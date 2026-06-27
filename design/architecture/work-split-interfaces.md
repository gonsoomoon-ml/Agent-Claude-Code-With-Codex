# 작업 분할 + 인터페이스 계약 (parallel workstreams)

> **목적:** 4개 주요 작업을 *두 사람이 충돌 없이 병렬*로 진행하고 병합하기 위한 day-one 합의 문서.
> **원칙:** **우리 DI seam 이 곧 병렬화 경계다.** 인터페이스(계약)를 먼저 *얼리고*, 레이어별로 나눠 각자 *다른 파일*을 만진다.

## 0. 5개 작업

1. **Gateway** — AgentCore Gateway 로 *authed/유료 출처*에서 기사 수집 확대(공유 도구 카탈로그).
2. **Runtime 배포** — AgentCore Runtime 으로 프로모트(deploy 3종 + 컨테이너 + IAM).
3. **DB** — 기사·요약·verdict 영구 저장 → *다른 사용자가 같은 파이프라인을 재실행하지 않게* 공유 캐시.
4. **Web UI** — 사용자가 요구사항(출처·이메일·DEPTH·발송시각·렌즈)을 설정.
5. **Scheduler·전달** — 사용자별 발송시각(`send_hour`·`timezone`)에 파이프라인 실행 + **SES 이메일 발송**.

## 1. 2 레인 (한 사람 = 한 레인, 소유 모듈 disjoint)

```
LANE B — Delivery & UX (사람 B)
  ② Runtime 배포  → runtime/{deploy_runtime,invoke_runtime,teardown}.py · Dockerfile · IAM    ┐
  ⑤ Scheduler·SES → 새 scheduler/ + Lambda dispatcher · SES send  (②와 한 쌍 = production 전달) ┤ seam: run_briefing · DeliverFn · profile
  ④ Web UI        → web/ + api/ → profile.yaml(쓰기·검증) · 결과 표시                           ┘ seam: profile.yaml 스키마
  ───────────────────────────────── 통합은 *얼린 contract* 로만 ─────────────────────────────────
LANE A — Data Fabric (사람 A)
  ③ DB        → shared/stores/source_store(로컬→DDB/S3) + 새 card/verdict 캐시 층                    ┐ seam: SourceStore
  ① Gateway   → shared/{sources,curation} 의 fetch_article_fn ← Gateway 도구                  ┘ seam: FetchArticleFn
```

- **A(데이터 기반)** 이 `source_store·curation·sources` 를 *한 사람*이 소유 → ①③ 내부 충돌 0(둘 다 데이터층).
- **B(전달·경험)** 의 `runtime/·web/` 는 파이프라인 내부와 disjoint → ②④ 충돌 거의 0.
- **핸드오프:** B 가 ②로 클라우드 가동하는 동안 A 가 ③ DB 구축 → 이후 B 의 ④ UI 가 A 의 DB 위에 올라탐.

## 2. 얼릴 인터페이스 계약 4개 (병렬 시작 전 *합의 + 시그니처 고정*)

**C1 · FetchArticleFn** (①이 구현 / curation 이 호출 — `shared/retrieval/curation.py`):
```python
FetchArticleFn = Callable[[Source, int], Sequence[FetchedArticle]]
# Source(key, name, url, kind, lang, fragile) · FetchedArticle(source_key, url, title, raw_text, published_at)
# ①: Gateway-backed fetch 가 이 시그니처를 만족하면 curate(..., fetch_article_fn=gateway_fetch) 로 끼움. 파이프라인 무변경.
```

**C2 · SourceStore 인터페이스 + 캐시 스키마** (③이 구현 — `shared/stores/source_store.py`):
```python
class SourceStore(Protocol):                 # 로컬파일·DDB/S3 둘 다 만족
    def freeze(self, *, url, title, raw_text, fetched_at) -> FrozenSource: ...
    def get_source(self, source_id: str) -> FrozenSource: ...
# ★ "재실행 방지" 캐시 키 (decorrelation 고려):
#   - frozen source : content-addressed sha256 (이미 사용자 간 공유)
#   - certifier verdict : (source_id, claim_text) → CertVerdict  ← *user-blind* 라 사용자 간 공유 가능
#   - author card : (source_id, lens, skill_hash) → DraftCard    ← lens별(개인화)이라 같은 렌즈끼리 공유
#   가장 큰 절감 = 같은 (source, lens) 면 claude -p + codex 재호출 0.
```

**C3 · run_briefing** (②가 래핑 — `shared/pipeline.py`, 이미 추출됨):
```python
def run_briefing(settings, store, users, *, window_hours=24,
                 fetch_article_fn=None, draft_fn=None, revise_fn=None, verify_fn=None) -> list[UserBriefing]: ...
# UserBriefing(user_id, recipient, cards, email, published, quarantined)
# ②: @app.entrypoint 가 이걸 호출만(이미 그러함). 배포는 컨테이너·스케줄·IAM 만 추가.
```

**C4 · profile.yaml 스키마** (④가 쓰기·검증 — `users/<id>/profile.yaml` → `UserConfig`):
```python
UserConfig(id, recipient, type, sources: tuple[str], depth, lens, send_hour, timezone, skill_md)
# ④: UI 가 이 스키마로 profile 을 쓰고 *검증*(recipient 이메일·sources∈CATALOG·depth enum·send_hour). config.py 의 "검증=write 계층" TODO.
#   v1: 파일(users/<id>/). v1.5: ③ DB 로 백킹(같은 스키마 유지).
```

**C5 · DeliverFn** (⑤이 구현 — 어댑터/스케줄러가 `run_briefing` 뒤 호출):
```python
DeliverFn = Callable[[UserBriefing], None]
# 기본 = SES SendEmail(to=briefing.recipient, html=briefing.email, from=settings.ses_sender). 테스트는 fake(발송 0).
# ★ SES sandbox: 수신자 사전 verify · @gmail 발신은 DMARC 거부 → 커스텀 도메인. QUARANTINE 은 발송 안 함(render 가 이미 제외).
```

**C6 · users_due_now** (⑤이 구현 — 타임존 due-check, *순수·테스트가능*):
```python
def users_due_now(users: Sequence[UserConfig], now_utc, *, granularity_h: int = 1) -> list[UserConfig]:
    ...  # 각 user: now_utc → user.timezone 변환한 local hour == user.send_hour 면 due.
# 시간 버킷팅 → EventBridge 시간당 1회 tick + Lambda dispatcher 가 due 사용자만 run_briefing+deliver
#   (per-user 규칙 X → 사용자 수와 무관하게 규칙 1개, 확장). ★ 중복 발송 방지(같은 날 이미 발송) = ③ DB sent-log(v1 stateless 가능).
```

## 3. 의존성 · 우선순위 · 첫 병렬 쌍

- **③ DB 가 토대** — ④ UI 가 사용자 설정·결과를 저장·표시하려면 DB 필요(파일로 시작 가능, 곧 DB).
- **② 배포는 독립** — 파이프라인 안정. 먼저 해서 클라우드 가동 추천.
- **⑤ 스케줄·전달은 ②와 한 쌍** — 스케줄러가 *배포된 runtime* 을 invoke(production). 단 dispatch·SES·타임존 로직은 *로컬에서 `run_briefing` 으로 개발·테스트* 가능. 중복 발송 dedup 은 ③ DB soft-dep(v1 stateless 가능).
- **① Gateway 는 후순위(v2)** — invariant 상 *authed/유료 출처·공유 도구 카탈로그*일 때만 값(공개 RSS 엔 불필요).
- **첫 병렬 쌍 = ③(A) + ②⑤(B)** — 토대·독립·둘 다 다음 쌍(①④)을 풀어줌. **둘째 쌍 = ①(A) + ④(B)**.

## 4. 두 작업 동시 진행 → 병합 워크플로

```
1) 위 C1–C4 시그니처를 *먼저 확정*(이 문서) — 가장 중요한 한 걸음
2) git worktree/branch 각 작업별 — 각자 *자기 모듈 + 얼린 인터페이스*만 수정
3) 상대편은 *DI fake 로 스텁*(이미 가능: fake fetch_fn/store/users) → 서로 안 기다림
4) 파일 disjoint + 인터페이스 frozen → merge 충돌 최소. seam 에서 통합 테스트
5) contract 변경 필요 시 *공동 결정*(둘 다 rebase). 계약은 자주 바뀌면 안 됨
```

## 5. 작업별 상세 (scope · 소유 파일 · 끼우는 contract · done-when)

| # | scope | 소유 파일 | contract | done-when |
|---|---|---|---|---|
| ② | toolkit `Runtime.configure().launch()` + invoke + teardown; root `.env` 에 ARN writeback; `bedrock-agentcore-starter-toolkit` dep | `runtime/deploy_runtime.py·invoke_runtime.py·teardown.sh` (Dockerfile·requirements 존재) | **C3** run_briefing | 실 AgentCore 에 1회 invoke → 사용자별 결과 SSE; teardown 동작 |
| ⑤ | EventBridge 시간당 tick → Lambda dispatcher(`users_due_now`) → `run_briefing` + **SES 발송**; sent-log dedup | 새 `scheduler/` + SES `deliver`(entrypoint 의 TODO(deliver) 채움) | **C3·C4·C5·C6** | gonsoo 의 07:00 KST 에 검증 브리핑이 받은편지함 도착(중복 발송 0) |
| ③ | SourceStore Protocol화 + DDB/S3 impl; (source_id,claim_text) verdict 캐시 + (source_id,lens,skill_hash) card 캐시; run_briefing/gate 에 캐시 조회 | `shared/stores/source_store.py` + 새 `shared/stores/cache.py` | **C2** SourceStore | 같은 (source,lens) 2회 실행 시 둘째는 claude -p·codex 0회(캐시 hit) |
| ① | Gateway MCP 클라이언트 + authed 출처 fetch → `FetchArticleFn`; JWT 정적 주입(headless) | 새 `shared/gateway.py` + `sources.py`(authed 항목) | **C1** FetchArticleFn | authed 출처 1건이 curate→freeze→gate 통과(공개 RSS 경로 무변경) |
| ④ | profile 쓰기·검증 API + 프론트(출처 선택·이메일·DEPTH·시각·렌즈) + 결과 뷰 | 새 `web/` + `api/` | **C4** profile.yaml | UI 에서 profile 생성 → 파이프라인이 그 사용자 브리핑 산출 |

---

**요약:** seam-기반 설계의 배당금 = "두 사람이 안 부딪히고 병렬." C1–C4 만 얼리면 나머지는 각 레인 안에서 자유다. 첫날 합의 = 이 문서 + 4 contract 시그니처.

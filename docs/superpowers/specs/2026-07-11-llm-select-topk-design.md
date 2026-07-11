# LLM top-K 선별(select) — 소스별 캡을 "최신순 잘림"에서 "내용 기반 선별"로

- **상태:** DRAFT (2026-07-11) → 구현
- **발단:** pytorch-kr-news vetting — 평일 6~9건/일(자동 큐레이션 봇, :30 정각 발행)·균질 품질. 실측 결론: `max_items` 캡은 최신순 잘림이라 **고정 시간대 사각지대**(fetch 22:00 UTC 직후~새벽 발행분 매일 유실)를 만든다. 사용자 결정: 캡 판단을 AI 판정자에게 위임(K=3, pytorch-kr만; aitimes 는 관찰 후).

## 1. 위치와 신뢰 속성 (relevance judge 와 동형)

curate 단계(author/certifier *이전*)의 **사전 필터 2호** — ① require_ai(YES/NO) 다음에 ② top-K 선별. 판정은 포함 여부만 결정하고 certifier 증거에 흘러들지 않음 → **decorrelation 무관**(relevance spec §3 논거 그대로). 실패 사다리도 동형: **주=Haiku pick-K, 폴백=최신순 캡(현행과 동일) + non-silent warn.**

## 2. 설계

### catalog / Source (소스별 opt-in)
- `max_items: int = 0`(0=글로벌 기본 5) — 소스별 캡 오버라이드(window_hours 와 대칭).
- `select: str = ""`("" = latest) — 캡 초과 시 선별 방식: `latest`(현행 잘림) | `llm`(Haiku pick-K).
- 로더 검증: max_items 는 0 이상 정수(bool 거부), select ∈ {"", "latest", "llm"} — 아니면 시작 시 크래시.

### 후보 풀(pool)
현행은 fetch 내부에서 캡 5로 끊어 6번째 이후를 판정자가 볼 수 없음 → `_default_fetch`:
`cap = source.max_items or 5` · `pool = 12 if select=="llm" else cap` 로 페치(일 8~9건 소스를 커버, 프롬프트 비용 유계).

### curate 선별 단계
fetch → require_ai 필터 → **len > cap 이면 chooser(articles, cap)** → freeze.
- chooser = `select_fn`(주입됨 && select=="llm") else `latest_k`(= 피드 최신순 첫 K = 현행 동작).
- 선별/탈락 제목 dprint — **기존에 무음이던 캡 잘림이 처음으로 관측 가능**(latest 경로 포함, aitimes 부수 혜택).
- 주입 fetch(fake/gateway)가 캡 초과 반환해도 이제 curate 가 방어적으로 캡 적용(동일 dprint).

### seam / 판정 / 배선
- `selection.py`: `SelectFn = (Sequence[FetchedArticle], k) -> list[FetchedArticle]` · `latest_k` · `llm_select(articles, k, *, invoke)` — 후보 N건(제목+리드 300자, 번호 목록) **1콜**, 응답 = 선택 번호 JSON 배열. 파싱: 첫 `[...]` 추출 → 범위/중복 검증 → 유효 ≥ k 면 앞 k, 아니면 폴백+warn. 예외 → 폴백+warn.
- rubric(고정): ① 주요 모델/플랫폼/릴리스 발표 ② 광범위 적용 도구·보안/생태계 영향 ③ 파급력 큰 연구 — 근접중복 지양, 주제 다양성 우선.
- `relevance_bedrock.make_bedrock_select(settings)` — 기존 `_client`/Converse 재사용, `maxTokens=64·temperature=0`, 모델 = `relevance_model_id`(Haiku).
- 배선: `agentcore_runtime` real 모드의 기존 `relevance_llm_enabled` 블록에서 `fns["select_fn"]` 주입(같은 클래스의 curate-stage Haiku 사전 필터라 플래그 공유 — 새 env 없음). `run_briefing`/`curate` 에 `select_fn` 파라미터(기본 None=latest — 테스트·로컬 무변경).

### 기각한 대안(재제안 방지)
- 기사당 이진 "중요한가?" 판정 — K 보장 불가(0건 또는 전부 통과 가능), 비교 판단이 본질이라 집합당 1콜이 맞음.
- render 단계(사용자별) 선별 — author/certifier 가 풀 전체(9건)에 돌아 ~$0.9/일 낭비. 선별은 비용 발생 전(curate)이어야 함(relevance 와 같은 논리).

## 3. 편입 소스: pytorch-kr-news

`https://discuss.pytorch.kr/c/news/14.rss` (Discourse news 카테고리 스코프) · kind rss · lang ko · category **커뮤니티**(신설) · `max_items: 3, select: llm` · require_ai 불필요(AI 전문) · window 오버라이드 불필요(분초 timestamp). vetting 근거: robots 일반 허용·RSS 200·전문 3~8k자·주 50토픽.

## 4. 비용

선별 1콜/일/소스(~12건 × 리드 300자 ≈ 4~5K in, 64 out) ≈ **$0.005/일**. 카드 비용은 캡과 동일하게 3건으로 제한(바뀌는 건 비용이 아니라 *어떤* 3건인가). 브리핑 +3장/일(커뮤니티 섹션) ≈ +$0.3/일.

## 5. 테스트 계획 (TDD)

1. sources: catalog 파싱(max_items=3·select=llm) + 검증(음수/비정수 max_items·미지원 select 거부).
2. selection: llm_select — 정상 인덱스 선택 / 잘못된 JSON→폴백+warn / 범위 밖 필터 / 부족→폴백 / len≤k 는 무호출 통과.
3. curation: pool 확대(select=llm 이면 12) 캡처 / 주입 select_fn 이 고른 것만 freeze / select 미지정 시 latest 잘림 + dprint / require_ai → select 순서.
4. bedrock: make_bedrock_select converse 조립(번호 목록·maxTokens64) + "[1,3]" 파싱 / 예외→latest 폴백.
5. pipeline: select_fn pass-through.
6. 회귀: 전체 스위트.

## 6. 배포·검증·후속

- **deploy_api + deploy_runtime 둘 다**(소스 추가 규칙) + **DDB 사용자 프로필에 `pytorch-kr-news` 추가**(sources 가 명시 리스트 — 없으면 아무도 미수신; H4 Scan 이라 재배포 불필요).
- live 검증: 배포 전 오늘 실피드(8건)로 Haiku 가 뭘 뽑는지 확인 + 다음 아침 발송에서 커뮤니티 섹션 3장.
- 후속(관찰 후): aitimes 에 `select: llm`(캡 이미 물림) · 본격 랭킹/근접중복 머지로의 승급은 이 seam 을 대체.

# World Monitor 에서 건진 것 — 채널 후보 + 서비스 아이디어

> **발단:** 2026-07-31 브리핑 카드(`pytorch-kr-news`) — "World Monitor: 500여종의 뉴스와 지표들을 종합하여 실시간으로 보여주는 글로벌 정보 대시보드(OSINT)".
> **상태:** 전부 **미검증**. 어떤 항목도 아직 `catalog.yaml` 이나 설계에 반영되지 않았다.

## 0. 출처와 확인 방법

| 항목 | 값 |
|---|---|
| 포럼 글 | https://discuss.pytorch.kr/t/world-monitor-500-osint/11457 |
| 리포지토리 | `github.com/koala73/worldmonitor` — **AGPL-3.0-only** (별도 상용 라이선스 존재) |
| 규모(2026-07 기준 보도) | GitHub 65,500+ stars · 116 contributors · 외부 데이터 제공자 65+ |

**확인 방법(중요):** 카드 요약만 읽고 쓴 문서가 아니다. `gh api` 로 리포지토리를 직접 열어 아래 4개 파일을 읽었다 —
`src/config/feeds.ts`(피드 레지스트리, 1105줄) · `.github/workflows/feed-validation.yml`(피드 검증 CI) ·
`server/_shared/source-tiers.ts`(소스 티어) · `.github/ISSUE_TEMPLATE/new_data_source.yml`(소스 제안 인테이크).
아래 인용한 수치·주석은 그 파일들에서 온 것이다.

---

## 1. ★ 가장 큰 발견: "500 피드"의 실체는 큐레이션이 아니라 **검색-피드 기법**

`feeds.ts` 를 열어 보면 항목 상당수가 발행처 RSS 가 아니라 이런 모양이다:

```
https://news.google.com/rss/search?q=Anthropic+Claude+AI+when:7d&hl=en-US&gl=US&ceid=US:en
https://news.google.com/rss/search?q=AI+regulation+OR+"artificial+intelligence"+law+when:7d&...
```

**Google News 검색 결과를 RSS 로 받는다.** 그래서 "AI 규제" · "반도체" · "유니콘" · "EU AI Act" 같은
*주제* 를 발행처 협상 없이 피드로 만들 수 있고, 이것이 500이라는 숫자의 정체다.

### 유혹적인 이유
채널 확대의 지름길이다. 발행처를 하나씩 vetting 하는 대신 질의문 한 줄로 커버리지가 생긴다.

### 우리가 **발행 경로로는 쓸 수 없는** 이유 (셋 다 치명적)

1. **robots.txt AI 옵트아웃 우회가 된다.** 검색 결과 링크는 결국 TechCrunch · The Verge · Ars Technica ·
   VentureBeat · MIT Tech Review 로 간다 — `design/research/candidate-ai-media-sources.md` 가 **ClaudeBot/GPTBot
   명시 차단**을 이유로 이미 기각한 바로 그 매체들이다. Google 을 한 단계 끼운다고 발행처 의사가 바뀌지 않는다.
   저장소 원칙(`_http_get`: 접근통제 우회 없음) 위반.
2. **본문이 없다.** Google News 항목은 리다이렉트 URL + 제목/스니펫이다. trafilatura 전문 추출이 실패하고
   피드 스니펫만 남는다 — **`openai` 소스를 죽인 SEO 스텁 사고와 완전히 같은 실패 형태**다
   (`MIN_SOURCE_CHARS=500` 게이트가 라이브 19건을 전부 컷했던 그 건). 게이트가 잘 막아 주겠지만, 막는다는 건
   채택 0건이라는 뜻이다.
3. **중복 폭증.** 같은 사건을 N개 매체가 쓰므로 하루 카드 예산 안에서 dedup 부담만 커진다.

> **World Monitor 가 되는데 우리는 안 되는 이유:** 그들은 제목·스니펫을 **대시보드에 표시**한다.
> 우리는 본문을 **LLM 에 넣어 요약**한다. 같은 피드라도 사용 방식이 다르면 허용 여부도 다르다.

### 단, 한 조각은 살릴 수 있다 → **감사(audit) 전용** (아래 아이디어 ④)
발행이 아니라 "우리가 오늘 무엇을 놓쳤나"를 재는 데만 쓰면 본문을 가져올 필요가 없다 → robots 문제도 없다.

---

## 2. 채널 후보 (news channels)

**전부 vetting 전이다.** 각각 README 의 게이트 3단계(robots → curl → `fetch_clean_rss` + Sponsored 실측 →
`MIN_SOURCE_CHARS`)를 통과해야 `catalog.yaml` 에 들어갈 수 있다. 아래 "판단" 열은 조사 전 사전 예상일 뿐이다.

### A. 검토할 만한 것 (World Monitor 피드 중 우리 결에 맞는 것)

| 후보 | 피드 | 왜 | 사전 예상 리스크 |
|---|---|---|---|
| **arXiv cs.AI / cs.LG** | `export.arxiv.org/rss/cs.AI` · `/cs.LG` | 1차 연구 원천. 회사 블로그 편중(자사 홍보)을 상쇄하는 각도 | ⚠️ RSS 가 **초록만** → 500자 게이트 경계. 그리고 초밀집 논문은 이미 알려진 **author 타임아웃 tail** 이다. `require_ai` 불필요 |
| **MIT News — Research** | `news.mit.edu/rss/research` | 대학 연구 발표, 광고 없음 | 종합 연구(생물·물리 섞임) → `require_ai` 필요 |
| **GitHub Blog** | `github.blog/feed/` | Copilot·에이전트·개발자 도구 1차 발표. `engineer` lens 와 정면으로 맞음 | 종합 → `require_ai` 필요 |
| **The New Stack** | `thenewstack.io/feed/` | AI 인프라·에이전트 운영 심층. 회사 블로그가 안 쓰는 각도 | 종합 클라우드 → `require_ai`. 스폰서 콘텐츠 비율 실측 필수 |
| **InfoQ** | `feed.infoq.com` | 엔지니어링 실무 심층 | 종합 → `require_ai`. 요약 스텁 여부 확인 |
| **Changelog** | `changelog.com/feed` | 오픈소스 생태계 | 팟캐스트 쇼노트 위주면 본문 부족 가능 |
| **Y Combinator Blog** | `ycombinator.com/blog/rss/` | 스타트업·AI 창업 각도 | 발행 빈도 낮음(quiet source) |
| **Tom's Hardware** | `tomshardware.com/feeds.xml` | 하드웨어 공백(NVIDIA 는 robots 로 기각됨) | 종합 하드웨어 → `require_ai`. robots 확인 필수 |
| **Stratechery** | `stratechery.com/feed/` | 전략 분석 — 「사실들을 엮으면」에 좋은 재료 | ⚠️ 유료 뉴스레터, 피드는 부분공개일 가능성 → **스텁 위험 높음** |

### B. 명시적으로 안 되는 것 (조사 낭비 방지)

| 후보 | 기각 이유 |
|---|---|
| Hacker News · Show HN · Lobsters · dev.to · GitHub Trending · TechMeme | **링크 애그리게이터** — 본문이 없다. 우리 파이프라인은 원문 전문을 요약·검증한다. 구조적 부적합 |
| TechCrunch · The Verge · Ars Technica · VentureBeat · MIT Tech Review · NVIDIA | **이미 기각됨**(robots AI 옵트아웃). World Monitor 가 쓴다는 사실은 우리 판단을 바꾸지 않는다 — §1 참조 |
| Google News 검색-피드 전반 | §1 — 발행 경로로는 불가. 감사 용도만 |
| 팟캐스트 피드(20VC · Masters of Scale · Pivot) | 쇼노트=메타데이터. 본문 없음 |

### C. 이미 대기 중인 후보 (중복 조사 금지)
`design/research/candidate-ai-media-sources.md` 에 vetting 까지 끝나고 **아직 미채택**인 것들이 있다 —
**Hugging Face** · **인공지능신문(aitimes.kr)** · **Microsoft Research** · **Import AI** · **Meta/Mistral(kind:html)**.
채널을 늘릴 거라면 **여기가 먼저다**. 조사 비용이 이미 지불됐고 robots 게이트도 통과했다.

---

## 3. 서비스 아이디어

### ① 피드 헬스 CI + **silent-zero streak** 감지 — 우선순위 1위

World Monitor 의 `feed-validation.yml` 은 542개 피드를 **매일 1회** 검증하고, 부가로
`news:feed-health:v1` 로 **"조용한 0건 연속(silent-zero streaks)"** 을 발행한다.

**이것이 우리의 OPEN 항목을 정확히 겨냥한다.** 우리는 두 번 당했다 —
`openai` 소스가 매일 19건을 warn 하면서 조용히 0건을 반환하던 기간, 그리고 카드 격리 사고 때의 무통지 미발송.
"실패했다"가 아니라 **"성공했는데 결과가 0이다"** 는 현재 아무도 안 본다.

훔쳐 올 것 — 설계 세부까지:
- **주기는 하루 1회면 충분하다.** 그들은 6시간 → 24시간으로 **낮췄고**, 주석에 이유가 적혀 있다:
  *"피드 장애는 그렇게 빨리 변하지 않는다. 542피드 × 4회/일 = 아무도 안 보는 러너 시간 낭비."*
- ⚠️ **`pull_request` 트리거 금지 — 보안.** 그들 주석 그대로: 적대적 PR 이 `feeds.ts` 를 고쳐
  **CI 러너가 임의 URL 을 때리게 만들 수 있다(SSRF)**. 트리거는 `push to main` + `schedule` + 수동만.
  우리도 `catalog.yaml` 이 정확히 같은 성질의 파일이다.
- 가드레일 3종: https 전용 · 도메인 allowlist 재확인 · **크로스호스트 리다이렉트는 홉마다 재검사**.

우리 구현 선택지(둘 다 유효, 결정 필요):
- **(a) GitHub Actions** — 현재 이 저장소엔 `.github/` 자체가 없다. 새로 도입하는 비용이 든다.
- **(b) 기존 CloudWatch 경로 재사용** — 우리는 이미 `warn → CloudWatch 메트릭` 집계가 있다(`38933ad`).
  "소스별 채택 0건이 N일 연속" 알람은 여기에 얹는 게 훨씬 싸고, 무엇보다 **실제 프로덕션 런의 데이터**를
  본다(CI 는 피드가 살아있는지만 알지, 우리 파이프라인이 실제로 카드를 뽑았는지는 모른다).
- 초안 의견: **(b) 를 먼저, (a) 는 나중에.** 우리가 놓친 건 "피드가 죽었나"가 아니라 "채택이 0이었나"다.

### ② 소스 티어 (source tier) — 해석층 재료로서

`source-tiers.ts` 는 소스를 4단계로 나눈다: **Tier1** 통신사/공식 기관 · **Tier2** 주요 매체 ·
**Tier3** 전문·지역·싱크탱크 · **Tier4** 애그리게이터·블로그. 미등록은 4로 폴백.

우리 `catalog.yaml` 은 flat 하다(`category` = 발행처 그룹, UI 섹션용). 티어가 생기면 두 군데서 쓰인다:
- **캡 초과 선별(`select: llm`)의 사전 가중치** — 현재 Haiku pick-K 가 관련성만 본다.
- ★ **해석층의 재료** — "이건 회사의 **1차 발표**이고 저건 **2차 보도**다"는 구분은
  「사실들을 엮으면」이 실제로 쓸 수 있는 사실이다. interp-v1.2 가 통찰을 4→36% 로 올린 원리가
  *재료를 바꾼 것*이었다는 점에서 결이 같다.

> ⚠️ **미끄러짐 주의:** 티어를 "중요도 점수"로 쓰기 시작하면 얇은 LLM 래퍼 쪽으로 간다(인클루전 테스트 3번).
> **검증·해석의 재료로만** 쓰고, 랭킹 자동화로 확장하지 말 것.

### ③ 소스 제안 인테이크 템플릿

그들의 `new_data_source.yml` 필수 필드: 소스 유형 · 대상 변형 · 이름 · 피드 URL · **"왜 추가하는가"**.
우리 vetting 절차는 이미 문서에 잘 적혀 있지만 **코드 옆에는 없다** — `catalog.yaml` 헤더 주석이
형식만 강제하고 vetting 은 사람 기억에 의존한다. 체크리스트를 `.github/ISSUE_TEMPLATE/` 또는
`idea-bank/` 체크리스트로 만들면 robots 확인 누락 같은 실수를 구조적으로 막는다.

### ④ 커버리지 감사 — "오늘 우리가 놓친 것" (검색-피드의 유일한 정당한 용법)

World Monitor 는 GDELT 대비 **recall benchmark** 를 돌린다. 우리 버전:

- Google News 검색-피드(`"artificial intelligence" when:1d`)에서 **제목만** 수집한다 — 본문 미수집 → robots 무관.
- 원장(ledger)에 이미 있는 "오늘 다룬 것"과 대조 → **카탈로그 공백을 데이터로 발견**한다.
- 산출물: "어제 AI 뉴스 N건 중 우리 카탈로그가 닿지 않은 주제 M건" → 다음 소스 추가의 근거.

★ **이것이 인클루전 테스트를 통과하는 형태다.** 원장이라는 지속 상태가 이미 있어 diff 가 가능하고,
결과가 일회성 리포트가 아니라 카탈로그를 진화시킨다. (반면 이걸 사용자 대면 기능으로 만들면 탈락 — 내부 도구로.)

### ⑤ MCP 도구 표면 분리 — v-next 참고

카드의 해석층이 짚었던 바로 그 포인트: **`tools/list` 는 무인증 공개, `tools/call` 만 인증**.
"역량 발견은 공개, 실행은 인증"이라는 분리다.

우리 ① Gateway 는 이미 MCP + Cognito CUSTOM_JWT 이고, dispatch 화이트리스트 = retrieval 3도구다.
현재는 off-by-default 이고 v1 에선 load-bearing 이 아니라고 정직하게 기록돼 있다. 이 패턴은
**author 를 MCP-pull 로 바꾸는 v-next** 때 참고 가치가 있다.

> ⚠️ **불변 가드레일:** 무엇을 하든 `gate`/`certify`/`author`/`freeze` 는 도구로 노출하지 않는다.
> decorrelation 이 무너진다. World Monitor 는 검증자가 없는 제품이라 이 제약이 없다 — 따라 하면 안 되는 부분.

---

## 4. 기각 (인클루전 테스트 위반 — 재제안 금지)

| 기능 | 기각 이유 |
|---|---|
| 지도 UI(globe.gl 3D + deck.gl 평면, 56 레이어) | 우리는 이메일 제품. 범위 밖 |
| **국가 불안정 지수(CII v8) 류 파생 지수** | 매력적이지만 **verify-before-publish 와 상극**이다. 합성 지수는 certifier 가 재도출할 원문 구절이 없다 → 우리 신뢰 구조에서 검증 불가능한 유일한 종류의 산출물. 만들면 그 카드만 무검증이 된다 |
| Tauri 데스크톱 앱 · 6개 사이트 변형 | 범위 밖. "단일 코드베이스 → 변형"은 우리 lens(general/engineer/business/researcher)와 개념적으로 이미 동형 — 새로운 것 없음 |
| Ollama 로컬 모델 구동 | 우리는 **cross-family 두 하니스**가 신뢰의 원천이다. 로컬 단일 모델은 decorrelation 붕괴 = 제품의 존재 이유 소멸 |
| 실시간 대시보드 전반 | 인클루전 테스트 3번(기본 프리미티브 초과)에도, 제품 정의(**가벼운 아침 브리핑**, 딥리서치 생성기 아님)에도 어긋남 |
| Google News 검색-피드를 발행 경로로 사용 | §1 — robots 우회 + 본문 스텁. 감사 용도(④)만 허용 |

---

## 5. ⚠️ 라이선스

**AGPL-3.0-only** (상용 라이선스 별도, 상표 사용 별도 허가).

- **코드 복사 금지.** AGPL 은 네트워크 서비스로 제공만 해도 전체 소스 공개 의무가 발생한다(§13).
  우리 서비스에 그들 코드를 넣으면 우리 저장소 전체가 걸린다.
- **아이디어·기법은 자유.** 저작권은 표현을 보호하지 CI 주기나 티어 개념을 보호하지 않는다.
  위 ①~⑤ 는 전부 안전하게 따라 해도 된다 — 우리 코드로 새로 쓰는 한.
- **피드 URL 목록은 회색지대.** 개별 URL 은 사실이지만 *선별·배열*은 편집저작물 주장 여지가 있다.
  → **통째 복사 금지.** §2 처럼 개별 후보로 뽑아 각각 우리 기준으로 vetting 해서 채택할 것.

---

## 6. 다음 액션

- [ ] **채널:** §2-C 먼저 소진 — 이미 vetting 끝난 Hugging Face · 인공지능신문 · Microsoft Research · Import AI 채택 결정
- [ ] **채널:** §2-A 중 상위 2~3개 vetting(robots → curl → `fetch_clean_rss` → Sponsored/스텁 실측)
- [ ] 소스 추가 시 **배포 2종 필수**: `deploy_api` + `deploy_runtime` (⚠️ `deploy_scheduler` 는 금지 — dry-run 리셋 풋건)
- [ ] **아이디어 ①**(silent-zero 감지) 설계 — (a) CI 냐 (b) CloudWatch 냐 결정 필요 ← **아래 판단 대기**
- [ ] **아이디어 ②**(소스 티어) — 채택 시 `catalog.yaml` 스키마 변경 + `_load_catalog` 검증 추가
- [ ] 아이디어 ④(커버리지 감사)는 ①·② 이후 — 선행 의존 없음이나 우선순위 낮음

---

## 7. 열린 결정 — silent-zero 임계값 정책 (미작성)

①을 구현하려면 **"언제 알리는가"** 를 정해야 하는데, 이건 코드 문제가 아니라 운영 판단이다.

**계측 지점은 이미 존재한다** — `src/briefing/core/pipeline.py`의 `run_briefing`:
`fetch_set()` 결과(`by_key`, 소스별 **fetch 건수**)와 `produced`/`cards`(소스별 **채택 건수**)가
같은 함수 안에 둘 다 있다. 즉 "N건 받아서 0건 발행"을 지금 바로 셀 수 있고, 새 배관이 필요 없다.
(`gate.py` 는 카드 단위 판정만 하므로 여기가 아니다. 소스 레벨 스텁 경고는 `sources.py:306` 에 이미 있다.)

정해야 할 것:

```python
# 소스가 "조용히 0건"일 때 언제 사람을 부를 것인가?
#
# 고려사항:
#  - anthropic-eng · claude-blog · YC Blog 는 정상적으로 며칠씩 0건이다(quiet source).
#    임계값이 낮으면 매일 우는 알람이 되고, 알람 피로가 쌓이면 진짜 사고를 놓친다.
#  - 반대로 openai 소스는 19건을 fetch 하고 0건을 채택하며 몇 주를 조용히 보냈다.
#  - 구분 신호가 하나 있다: "fetch 0건"(발행이 없었다 = 정상)과
#    "fetch N건인데 채택 0건"(게이트가 다 잘랐다 = 이상)은 완전히 다른 사건이다.
#
# TODO: 임계값 정책 — 소스별 고정 N일? 소스의 평소 발행 빈도 대비 상대값?
#       아니면 fetch>0 & 채택=0 만 즉시 알리고 fetch=0 은 아예 안 보나?
```

이건 우리 소스들의 평소 리듬을 아는 사람이 정해야 정확합니다 — 제가 기본값을 찍으면
`anthropic-eng` 같은 quiet source 를 사고로 오인하거나, 반대로 놓칠 겁니다.
</content>
</invoke>

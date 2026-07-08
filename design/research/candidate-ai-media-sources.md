# 추가 후보 AI 미디어 리서치 (Candidate AI media sources) — 2026-07-08

카탈로그(`src/briefing/core/retrieval/catalog.yaml`)에 **추가할 만한 AI 매체**를 조사·검증한 랜드스케이프 문서.
검증 = `curl`(HTTP 상태·content-type·`<item>`/`<entry>` 수·최신 제목) + 일부 `fetch_clean_rss`(우리 파이프라인 실추출). 아직 **추가 전** — 선택용 메뉴.

## 현재 카탈로그 (12개, 발행처 기준)
| 섹션 | 소스 |
|---|---|
| 뉴스·미디어 | AI Times (aitimes.com, ko) |
| Amazon (AWS) | AWS ML Blog · AWS Korea Tech Blog · AWS AI News |
| Anthropic | Anthropic News · Anthropic Engineering · Claude Blog |
| OpenAI | OpenAI News |
| Google | DeepMind · Research · The Keyword · Developers Blog |

**공백 진단:** ① 대형 랩 중 **Meta·NVIDIA·Microsoft·Mistral·Hugging Face 부재** · ② **독립 AI 미디어**(비판적 시각)가 AI Times 하나뿐(회사 블로그=자사 홍보 편중) · ③ 한국 매체 다양성 부족.

## ⚠️ 결정적 게이트: robots.txt AI 옵트아웃 (비협상 — 다른 조건보다 우선)
우리 제품은 **Claude author 로 요약**한다. AI 봇(ClaudeBot·GPTBot·anthropic-ai·CCBot 등)을 `robots.txt` 로 **명시 차단한 매체는 추가 금지** — generic UA 우회는 발행처 의사 위반 + repo 원칙("접근통제 우회 없음") 위반 + 현행 소송 패턴(NYT vs **Perplexity** RAG 스크레이핑). 기존 카탈로그가 전부 `robots Allow:/` 였던 게 이 기준.

| 후보 | AI 봇 robots | 판정 |
|---|---|---|
| The Decoder · Hugging Face · 인공지능신문(kr) | ✓ 차단 없음 | **추가 가능** |
| **TechCrunch · The Verge · Ars Technica · VentureBeat · MIT Tech Review · NVIDIA** | ⚠️ ClaudeBot/GPTBot/anthropic-ai 등 **명시 차단** | **추가 금지(AI 옵트아웃)** |
| *(대조: 현 카탈로그 Anthropic·OpenAI·AI Times)* | ✓ | — |

> **역설:** 명성 있는 대형 미디어일수록 AI 옵트아웃(TechCrunch·Verge·Ars·VB·MIT·NVIDIA 전부). 덜 유명한 The Decoder·HF·인공지능신문이 오히려 AI-friendly. **추가 전 반드시 robots.txt 부터 확인.**

---

## ① 프런티어 랩 / 기업 (신규 발행처 섹션 후보)

| 매체 | 피드 URL | 검증 | 메모 |
|---|---|---|---|
| **NVIDIA** | `https://blogs.nvidia.com/feed/` | ✓ 200 · 18건 | AI 하드웨어 거인, 큰 공백. 종합 블로그(게이밍·오토 섞임) → **require_ai** |
| NVIDIA (Developer) | `https://developer.nvidia.com/blog/feed/` | ✓ 200 · 100건 | 기술 심화·고빈도. 위 블로그와 택1 |
| **Hugging Face** | `https://huggingface.co/blog/feed.xml` | ✓ 200 · 820건(최신만 컷) | 오픈소스 AI 허브, **전부 AI**(require_ai 불필요) |
| **Microsoft (Research)** | `https://www.microsoft.com/en-us/research/feed/` | ✓ 200 · 10건 | "Agent skills as trainable parameters" 등 연구. **MS AI 블로그(`blogs.microsoft.com/ai/feed/`)는 410 폐기** → Research 가 대안 |
| Meta AI | ai.meta.com/blog | ⚠️ **RSS 없음** (autodiscovery none, `/feed/` 404) | `kind:html`(트래필라투라 리스팅, anthropic/claude-blog 방식)로만 가능 |
| Mistral AI | mistral.ai/news | ⚠️ **RSS 없음** (autodiscovery 실패, `/news/rss.xml` 404) | `kind:html` 필요 |
| DeepSeek / xAI / Cohere | — | ✗ 피드 없음 | DeepSeek 404 · Cohere rss.xml 0건 · JS 페이지, 취약 |

## ② AI 미디어 — 독립 저널리즘 (뉴스·미디어 섹션; 대부분 AI-scoped라 require_ai 불필요)

| 매체 | 피드 URL | 검증 | 메모 |
|---|---|---|---|
| ~~MIT Tech Review — AI~~ ⚠️ | `https://www.technologyreview.com/topic/artificial-intelligence/feed/` | ✓ 200 · 10건 | 본문은 잘 페치됨(5–8k자, 메터드 무차단). **하지만 최근 절반이 "Sponsored" 네이티브 광고**(예: "Sponsored The foundational elements of AI architecture…") → AI 주제라 require_ai 도 못 거름 → **브리핑에 광고 유입**. **보류/강등** |
| **The Decoder** ⭐ | `https://the-decoder.com/feed/` | ✓ 200 · 10건 | 전문 AI 뉴스·**광고 없음**·전문(1.3–4.9k자). MIT 대신 독립 미디어 **1순위** |
| **TechCrunch — AI** | `https://techcrunch.com/category/artificial-intelligence/feed/` | ✓ 200 · 20건 | 속보·스타트업·비즈니스 |
| **Ars Technica — AI** | `https://arstechnica.com/ai/feed/` | ✓ 200 · 20건 | 기술·비판적 |
| **The Verge — AI** | `https://www.theverge.com/rss/ai-artificial-intelligence/index.xml` | ✓ 200 · 10건 | 소비자 AI |
| **VentureBeat — AI** | `https://venturebeat.com/category/ai/feed/` | ✓ 200 · 7건 | 엔터프라이즈 AI 비즈니스 |
| **Import AI** (Jack Clark) | `https://jack-clark.net/feed/` | ✓ 200 · 10건 | 정책·연구 뉴스레터(고신호) |
| Simon Willison | `https://simonwillison.net/atom/everything/` | ✓ 200 · 30건 | LLM 논평(dev 섞임 → **require_ai**) |

## ③ 한국

| 매체 | 피드 URL | 검증 | 메모 |
|---|---|---|---|
| **인공지능신문** (aitimes.kr) | `https://www.aitimes.kr/rss/allArticle.xml` | ✓ 200 · 50건 | AI Times(.com)와 **다른** 국내 AI 전문지. allArticle → **require_ai** 권장 |
| ZDNet Korea | `https://feeds.feedburner.com/zdkorea` | ✓ 200 · 30건 | **AI 전용 RSS 없음**(FeedBurner 종합 1개뿐). require_ai 시 ~40%만 AI + v1 필터 오탐(카드뉴스·실적 곁가지). AI Times 와 역할 겹침 → **비추천 경향** |

---

## 추천 (공백 메우기 + 품질, 우선순위 5)
**(robots.txt AI 허용분만 — 위 게이트 통과):**
1. **The Decoder** (`the-decoder.com/feed/`) — 독립 AI 미디어 1순위(heise 소속·광고 없음·**AI 허용**)
2. **Hugging Face** (`huggingface.co/blog/feed.xml`) — 오픈소스 AI 공백(전부 AI·**AI 허용**)
3. **인공지능신문**(`aitimes.kr/rss/allArticle.xml`, require_ai) — 국내 AI(단 AI Times 와 겹침, **AI 허용**)
4. **Meta / Mistral** (`kind:html`) — 마지막 대형 랩 공백, 단 **추가 전 robots.txt 확인 필수**

**❌ 추가 금지(robots AI 옵트아웃):** NVIDIA · TechCrunch · The Verge · Ars Technica · VentureBeat · MIT Tech Review — 아무리 좋아도 발행처가 AI 봇을 명시 차단 → 제외.

**강력 옵션:** Microsoft(Research) · Import AI · 인공지능신문(kr).

## 주의 (Caveats)
- **require_ai 필요:** 종합 피드(NVIDIA blog·Simon Willison·인공지능신문 allArticle·ZDNet)는 AI 무관 기사가 섞여 필터 필수. v1 키워드 필터는 **정밀도 제한**(오탐: "카드뉴스 범죄", 곁가지: 실적 뉴스).
- **RSS 없는 랩(Meta·Mistral):** trafilatura `kind:html` 리스팅 페치만 가능 — anthropic/claude-blog 와 동형(취약도 낮음)이나 사이트별 실추출 확인 필요.
- **중복:** ZDNet Korea·인공지능신문은 AI Times 와 커버리지 겹침(국내 종합) — 둘 다 넣으면 국내 잡음↑. 각도 다른 한 곳만 권장.
- **회사 블로그 vs 미디어:** 랩 블로그는 자사 발표(1차 사실), 미디어는 비판·맥락 — 브리핑 균형상 **둘을 섞는 게** 좋음.
- **⚠️ 광고 오염(Sponsored) — 명성 ≠ 깨끗한 피드:** MIT Tech Review AI 피드는 최근 절반이 "Sponsored" 네이티브 광고였음(실측). AI 주제라 `require_ai` 도 못 거르고 verify-before-publish 로도 걸러지지 않음(광고는 "사실"이라 통과) → **브리핑에 광고 카드 유입**. **추가 전 반드시 `fetch_clean_rss` 로 최근 항목의 Sponsored/네이티브 광고 비율을 실측**할 것. HTTP 200·유명 매체여도 방심 금지.

## 다음 단계
1. 추가할 소스 **선택** → 각각 `fetch_clean_rss` 실추출 vetting(우리 파이프라인 통과 확인, AWS/ZDNet 방식).
2. `catalog.yaml` 편집(발행처 섹션 배치 + require_ai/kind/homepage) + `catalog_categories` 자동 반영.
3. 배포 = **`deploy_api` + `deploy_runtime`**(소스 추가는 기능 변경 — 런타임이 실제 fetch). 참조: [[catalog-publisher-taxonomy]].
4. 브랜치 주의: 현재 `feat/admin-monitoring` — 카탈로그 변경은 **main 커밋 권장**.

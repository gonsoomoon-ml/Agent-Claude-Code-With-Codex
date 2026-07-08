# 카탈로그 발행처(publisher) 재편 + AWS Korea Tech Blog 추가 — 2026-07-08

**상태: SHIPPED · LIVE** (웹 picker + 런타임 이메일 밴드) · 커밋 `2bc00a6` · `71e9989` · `1b3b73e`

## 무엇을 (What)
소스 선택 섹션을 **콘텐츠 유형 → 발행처(publisher) 기준**으로 재편. 한 브랜드(Anthropic·Google)가 여러 섹션에 흩어지던 문제 해소. 이어서 **AWS Korea Tech Blog(ko)** 추가.

## 섹션 (순서 = catalog.yaml 파일 순서)
| 섹션 | 미디어 |
|---|---|
| 뉴스·미디어 | AI Times |
| Amazon (AWS) | AWS ML Blog · **AWS Korea Tech Blog** · **AWS AI News** |
| Anthropic | Anthropic News · Anthropic Engineering · Claude Blog |
| OpenAI | OpenAI News |
| Google | DeepMind · Research · The Keyword · Developers Blog |

## 결정 (Decisions)
- **주 축 = 발행처** (A안). "발행처"와 "콘텐츠 유형"은 직교라 한 축으로 묶으면 다른 축이 흩어짐 → 콘텐츠 유형 유지안·하이브리드(B, Google 재분산)는 기각.
- **순서 = 사용자 지정**: 뉴스·미디어 → Amazon (AWS) → Anthropic → OpenAI → Google. `build_catalog` 이 CATALOG(파일) 순서 보존하므로 **발행처 그룹을 파일에서 인접·정렬**해 통제.
- `category` 는 **웹 picker + 이메일 분야 밴드 공통 그룹핑 키** → 두 표면 동시 반영(그래서 런타임도 재배포 필요).

## AWS Korea Tech Blog (신규 소스)
- `https://aws.amazon.com/ko/blogs/tech/` · feed `…/feed/` · **kind rss · lang ko · category Amazon (AWS) · require_ai true**(종합 기술 블로그 — AI 관련만 통과).
- **vetting**: curl RSS 200 `application/rss+xml` 10 items; `fetch_clean_rss` 로 6건 추출(Bedrock AgentCore·Strands Agents SDK·Agentic AI·벡터검색 등 AI 관련 다수) → 파이프라인 통과 확인. homepage 오버라이드(피드 호스트=회사 대문).

## AWS AI News (신규 소스 2 — `anthropic.com/news` 격) · 커밋 `c372548`
- `https://aws.amazon.com/blogs/aws/category/artificial-intelligence/` · feed `…/feed/` · **kind rss · lang en · category Amazon (AWS)**.
- AWS News Blog 의 **Artificial Intelligence 카테고리** = 공식 AI 제품·서비스 발표(Bedrock·모델 출시·AgentCore·Summit). **이미 AI-scoped → require_ai 불필요**(기존 ML/KR 블로그는 종합이라 require_ai=true 였던 것과 대비). 기존 AWS ML Blog(기술 how-to)와 역할 구분 = 발표 채널.
- vetting: curl RSS 200 `application/rss+xml` 20 items; `fetch_clean_rss` 6건(Claude Sonnet 5 on AWS·Grok 4.3 in Bedrock·Bedrock Managed KB·Web Search on AgentCore).
- 후보 비교: News Blog AI 카테고리(채택) > generative-ai 서브카테고리(더 좁음) > ML Blog announcements(기존 aws-ml 과 중복).

## 배포 (두 표면 모두 — 소스 추가는 기능 변경이라 런타임 필수)
- **API Lambda 재배포** → 웹 picker `/catalog`. 라이브 검증(섹션 순서·매핑·신규 소스 스크린샷).
- **AgentCore 런타임 재배포**(CodeBuild ARM64, launch 73s, READY) → ① 신규 소스 fetch 가능(picker-only면 선택했는데 못 가져오는 silent failure) ② 이메일 밴드 = 발행처 이름. **런타임 READY = 새 catalog 컨테이너 로드 성공(= 검증)**.
- **스케줄러 무변경(중요)**: 런타임 in-place 업데이트라 **ARN 불변**(`…b9uh7rDAqL`) → `briefing-scheduler-dispatch` env 그대로 매칭, `BRIEFING_DRY_RUN=0`(실발송) 보존. **deploy_scheduler 재실행을 피해 dry-run 풋건을 건드리지 않음**.

## 검증 (Verification)
- ruff clean · pytest **214 passed**(+3 skipped) · `test_pipeline` 밴드 단언 갱신(aitimes→뉴스·미디어, openai→OpenAI).
- 라이브 `/catalog`(섹션 순서·매핑) + 웹 picker 스크린샷 · 런타임 READY · 스케줄러 ARN/DRY_RUN 실조회 확인.

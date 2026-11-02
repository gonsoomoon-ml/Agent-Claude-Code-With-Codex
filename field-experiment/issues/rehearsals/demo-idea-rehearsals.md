# 주간 Applied AI 데모 아이디어 기사 — 리허설 4편(AWS 기준) + 프론티어 기준 재작성 2편 + 축약판 1편 (2026-10-25)

**상태:** 리허설(발송 안 함) · 첫 실전 = 2026-10-31(토) 05:00 KST run 뒤 손으로 · 수신자 = 사용자 본인
**PRD:** `summarize-prd.md` · **검토 경위:** `summarize-review.md`

## 0. 요약 — 확정 기준 (2026-10-25 결정)
- **발송:** 매주 토요일, 05:00 KST run(금요일 기사 포함)이 끝나 한 주 재료가 닫힌 뒤 "Applied AI 데모 아이디어 기사" 1편을 **별도 메일**(07:00~08:00 KST 목표). **데모 repo 는 분리** — 기사가 약속, repo 는 통과 시 후속 링크.
- **씨앗(하드 게이트, 셋 다 통과):** ① **프론티어 랩 1차 글** — Anthropic(Claude Blog·News·Engineering) > Google(DeepMind·Developers·Cloud AI) > OpenAI — 의 Applied AI·AI Agents 카드, 그 주 검증 통과(PUBLISH)만 ② 설계·SDK 수준으로 **재현 가능한 메커니즘**이 적혀 있을 것(발표문·수치만 있는 글은 탈락) ③ ⑤에 **AWS 경로**(Bedrock·Claude Platform on AWS·오픈소스)를 적을 수 있을 것 — 없으면 "AWS 경로 없음·확인 필요"로 표기하고 순위를 내린다(탈락은 아님).
- **소프트 순위:** ① 같은 주 프론티어 글 2편 이상이 한 그림으로 모이는가 ② 월요일 실행 가능성 ③ AWS 경로의 선명도 ④ 그 주 프론티어 역량(새 API·기능)을 끼울 수 있는가.
- **보강층(씨앗 금지):** AWS 고객 사례·참조 아키텍처(⑤ "AWS 에서 돌리면"의 근거), Safety·Industry 등 다른 영역 카드, 2차 보도(The Decoder 등). 모델 출시 글은 ⑧로.
- **씨앗 없는 주:** Anthropic → Google → OpenAI 순으로 찾고, 없으면 **"이번 주 아이디어 없음"**. AWS 사례를 씨앗으로 빌리지 않는다.
- **표기 5등급:** ✓ 출처 사실 · 제안(우리 설계) · 미검증(출처 밖 지식) · 격리(일간 게이트 QUARANTINE — 수치 인용 금지) · 확인 필요(가용성 등 출처에 없는 사실). 신모델·가용성은 list-foundation-models / list-inference-profiles 로 당일 확인.
- **"비즈니스 가치 검증"** = 수치를 보여주는 게 아니라 **독자가 자기 데이터로 재는 자(⑦)를 함께 주는 것**. 프론티어 글의 수치는 거의 전부 조직 결과라 ⑦이 기사의 중심.
- **운영 전제:** 후보 글은 동결 원문(8,000자 절단) 대신 **원문 재수집**. OpenAI 1차 글은 카탈로그에서 SEO 스텁 → 씨앗으로 쓰려면 소스 보강 선행.

### 기사 섹션 (확정 · 2026-10-25 축약 개정)
**원칙:** 독자 메일 = 기사만, **3,000자 안(목표 ~2,600자)**. 표기 범례·선정(씨앗/보강/고르지 않음)·깔때기·확인 필요 항목은 **내부 run 로그**로 분리. 출처 사실이 기본값(✓ 표기 없음), 우리 설계는 "제안" 소제목으로만 구분, 조직 결과 수치는 "(조직 결과)" 한 번. 한 사실은 한 번만 — 근거(②)에 쓴 것을 ③·④에서 재진술하지 않는다.

| # | 섹션 | 분량 | 내용 |
|---|---|---|---|
| 0 | 제목 + 기간·이번 주 글 3편 + 데모 한 줄 | ~250자 | 제목은 한 줄, 수식어 없이 |
| ① | 어떤 문제인가 | ~250자 | 독자가 월요일에 자기 시스템을 떠올릴 문장 |
| ② | 이번 주 근거 | ~1,000자 | 글 하나당 2~3문장, 최대 3편 · 「엮으면」 1문장 · 같은 주 AWS 사례는 여기 한 줄 |
| ③ | 데모 (제안) | ~800자 | A/B 두 안 각 2줄 · 공통 1줄 · 판정 규칙 1줄(=측정) · 순서 4단계(기록 항목 포함) · "AWS 에서 돌리면" 1줄 · **시작점(코드) 목록 ≤3줄**(저장소 — 파일·디렉터리: 어느 안/단계) · **"내 시스템에 대입" 1줄(필수 — "자를 함께 준다"가 여기 산다)** |
| ④ | 이번 주 역량으로 바꿔 끼우면 | ~200자 | 2줄 |
| — | 출처 | | URL 3개 |

2026-10-25 2차 축약: 질문/재는 값/비교점 표(구 ④)는 **삭제** — 다섯 행 중 셋이 ③의 판정 규칙·기록 항목의 질문형 재진술, 둘은 ①의 통찰 재질문이었다. 측정은 ③의 판정 규칙과 기록 항목이 맡고, "내 과제에 재 보라"는 요청은 ③ 마지막 줄 한 문장으로 남긴다(삭제 금지). 결과 약 2,600자, 표 없음.

**2026-10-31 시작점(코드) 규칙**(사용자 승인 "sounds good"): 저장소 링크는 **데모 기사 ③의 '시작점(코드)' 목록에만**(②·④·출처에 없음, 데일리 브리핑 메일·`src/briefing` 에는 넣지 않음). 고르는 순서 = ① 씨앗 글이 직접 가리키는 저장소 → ② 그 랩의 공식 SDK·쿡북 중 메커니즘을 구현한 **파일·디렉터리까지** 적을 수 있는 것 → ③ AWS 경로 저장소 1개 → ④ 서드파티는 그 저장소 자체가 메커니즘일 때만(리허설 1의 LiteLLM). 최대 3줄, 각 줄 = 저장소 — 파일: 어느 안/단계. **인기도는 기준이 아님**(스타 수는 생존 신호로 run 로그에만; "이번 주 인기 저장소" 칸 없음). **당일 링크 확인이 조건**(리다이렉트 해소 → 최근 push → README/경로에 메커니즘 이름; 10-30 점검에서 후보 15개 중 4개가 이름 변경 — anthropic-cookbook→claude-cookbooks · adk-samples→adk-recipes · strands sdk-python→harness-sdk · amazon-bedrock-agentcore-samples→awslabs/agentcore-samples). 확인 못 하면 링크 없이 보낸다. 분량은 링크 주소를 뺀 글자 수로 센다(메일에선 앵커로 렌더).

구 ①~⑧ 뼈대(재현 vs 조직 고유 · 구현 순서 · 체크리스트 · 측정이 따로)는 같은 사실을 네 번 말하게 해 6,600자가 됐다(1-B 원판 측정: "세 조건" 5회·"80%" 6회·✓ 30개). 원판은 아래 리허설 1-B 에 기록용으로 남긴다.

## 0-B. 기준 수정 경위 (2026-10-25, 사용자 피드백 → §0 에 확정 반영)
사용자: "I am more interested in advanced applied AI from frontier companies such as anthropic, openai and google. also, anthropic's blogs are interesting to me rather than the four cases you made."
- **씨앗 = 프론티어 랩 1차 글**(Anthropic Claude Blog·News·Engineering > Google DeepMind·Developers·Cloud AI > OpenAI). 리허설 1~4 의 씨앗(AWS 고객 사례·참조 아키텍처)은 **보강층 "AWS 에서 돌리면"** 으로 내려간다.
- 하드 게이트 "소형 AWS" → "Claude Platform on AWS 또는 Bedrock 에서 재현 가능"으로 완화. ⑧ 은 "이번 주 모델" → **"이번 주 프론티어 역량"**.
- 단서: OpenAI 1차 글은 카탈로그에서 SEO 스텁(The Decoder 경유 2차) → 씨앗으로 쓰려면 소스 보강 선행. 프론티어 글의 수치는 거의 전부 조직 결과 → ⑦ 측정 설계가 여전히 중심.
- 새 기준으로 같은 4주의 씨앗: 10-17~23 Anthropic "When to fold subagents" + Google "Governed Self-Evolving Agents" · 10-10~16 Anthropic "Redesigning source control" + Vercel eve + adk-recipes · 10-03~09 Cresta(Agent SDK) + Claude Code mods + 1,000-agent dynamic workflows · 09-26~10-02 Asana + Managed Agents/OpenShell + 영업 인바운드 → **리허설 4-B·1-B 로 재작성(아래)**. 프론티어 기준에서는 AWS 사례가 "AWS 층"으로 내려가고, 효과 수치는 전부 "방향만", ⑦이 비교 벤치(접기 전/후·금고 전/후) 형태가 된다.

## 리허설에서 드러난 것
| | 리허설 1 (10-17~23) | 리허설 2 (10-10~16) | 리허설 3 (10-03~09) | 리허설 4 (09-26~10-02) |
|---|---|---|---|---|
| 씨앗 | F&F LiteLLM 게이트웨이 | SD바이오센서 + CJ올리브영 | GS에너지 + 경신홀딩스 | Adjudicated Query + 계약 인텔리전스(AWS ML Blog 참조 아키텍처) |
| 보강 | LiteLLM 공급망 공격(Safety) | Google 에이전트 평가 · OECD | Quick ACL · Zenity · DevOps Agent·Postman | 앰비언트 에이전트 · Asana |
| 효과 수치 | 정성 | 없음 | 구조 수치(방향만) | 없음(참조 아키텍처) |
| 미검증 표기 | 0 | 0 | 0 | 0 |
| ⑧ 신모델 | 없음 | Grok 4.7(격리) | Haiku 5.5 | Sonnet 5.5 · GPT-6.1 Sol · **서울 in-region** |
| 운영 발견 | 원문 8,000자 절단 | 격리 카드 규칙 첫 적용 | AWS KR 사례 2건이 씨앗(3주 연속) | **한국 사례 0건인 주** — 씨앗이 AWS ML Blog 참조 아키텍처로 이동, 기사 성립 |
| 재료 수급 | 58 → 1 | 138 → 11 → 2 | 122 → 17 → 2 | 134 → 21 → 2 |

교훈: 수치가 없는 주가 오히려 좋은 데모 주일 수 있다(조직 결과 수치는 어차피 재현 불가). 같은 주 교차 영역 결합(F&F+LiteLLM 사건, SD+CJ, GS+경신+Quick+Zenity)이 기사를 "이번 주 것"으로 만든다. 세 주는 씨앗이 AWS Korea Tech Blog 고객 사례였고, 4주차(09-26~10-02)는 한국 사례가 없었지만 AWS ML Blog 의 참조 아키텍처 2건(실행 가능한 샘플 포함)으로 기사가 성립했다 — 씨앗 공급은 "AWS 두 블로그"에 걸려 있고, 고객 사례가 없는 주는 참조 아키텍처가 대체한다(효과 수치는 없으니 ⑦이 중심이 된다).

---

# 리허설 1 — 2026-10-17 ~ 10-23
## 사내 LLM 게이트웨이: 키 발급·모델 승인·예산 차단을 Bedrock 앞에 세우기


표기: ✓ = 이번 주 검증 통과 카드/동결 원문에 있는 사실 · 제안 = 우리 설계 제안 · 미검증 = 두 출처 밖 지식

## ① 어떤 문제인가
팀원들이 Claude Code 같은 AI 코딩 도구를 쓰고 싶어 하는데, Bedrock 키는 누가 어떻게 나눠 주고, 누가 얼마나 쓰는지 보고, 넘으면 멈출 수 있는가. ✓ F&F 는 최상위 모델을 이틀 시험 사용했을 때 기존 모델 대비 몇 배의 비용이 정상 과금된 사건을 계기로, 그 주말에 게이트웨이 구축을 시작했다. ✓ Bedrock 기본 기능은 알림(AWS Budgets)은 되지만 사용자·키 단위 실시간 차단, 키별 모델 허용, 셀프서비스 발급은 없다.

## ② 이번 주 근거
- ✓ F&F(AWS Korea Tech Blog, 10-18): LiteLLM proxy on EKS + 사내 포털 'LLM Lite'. 모델 접근 그룹 승인, 사용자(일)·프로젝트(월) 2계층 예산, 한도 초과 시 429 자동 차단, 80%/100% Slack·메일 통보, 발급 후 첫 호출까지 3분.
- ✓ LiteLLM v1.107.0 공급망 공격(PyTorch Korea 읽을거리, 10-23): 10-21 정식 릴리스 파이프라인이 악성 패키지를 서명·배포. 버전 미고정 pip install 과 latest 계열 Docker 태그 사용자가 영향. 복구 = 악성 파일 삭제 → 1.106.2 재설치 → 프록시 호스트가 닿던 비밀 전부 교체. 프록시 DB 에 상위 제공자 키가 모여 있어 한 대가 뚫리면 전체 키가 노출된다.
- 「사실들을 엮으면」(제안): 같은 주에 "LiteLLM 으로 비용을 막은 사례"와 "LiteLLM 자체가 공격당한 사례"가 나왔다. 게이트웨이는 비용의 단일 관문이면서 비밀의 단일 표적이다. 데모는 둘을 한 번에 다뤄야 한다.
- 고려했으나 고르지 않음: Octave(멀티테넌트 기반, 사용 사례당 배포 시간 50% 단축 ✓)·Bayer(감독 에이전트 + 22개 전문 에이전트, 질문 80% 자체 해결 ✓). 두 수치는 그 조직의 데이터·규모 위에서 나온 결과라 데모가 재현할 수 없고, 구조도 소형 AWS 범위를 넘는다.

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 키 발급 API, 모델 접근 그룹으로 미승인 모델 차단, 일/월 예산과 429(ExceededBudget), budget webhook 으로 80%/100% 통보. ✓ 전부 F&F 가 LiteLLM 네이티브 기능이라고 밝힌 것.
- 재현 안 됨(조직 결과): "몇 배의 비용" 사건의 크기, 3분이라는 온보딩 시간, EKS·Entra ID SSO·Argo CD 운영 체계. 독자 조직의 수치는 ⑦에서 직접 잰다.

## ④ 아키텍처 (제안 — F&F 구조를 소형화)
- 컨트롤 플레인: 발급·승인·예산 설정 — 데모에서는 포털 대신 CLI 스크립트 3개(issue-key / approve-model / set-budget).
- 데이터 플레인: LiteLLM proxy 1대(로컬 Docker 또는 ECS 1 task), Postgres 1개(키·spend), config.yaml 에 access_groups.
- 모델 백엔드: Bedrock Claude(일반 그룹) + 최상위 모델(restricted 그룹).
- 통보: budget webhook → 작은 수신 서버 → 콘솔 출력(Slack 은 선택).
- 로그: Bedrock invocation logging → CloudWatch Logs. ✓ F&F 는 현 규모에서 Athena·Firehose·QuickSight 없이 충분하다고 판단했다 — 데모도 같은 선을 지킨다.

## ⑤ 구현 순서 (제안)
1. 공급망 방어부터: ✓ 1.106.2 이상으로 버전 고정, Docker 는 digest 고정, 프록시 호스트는 사내망에서만. latest 태그 금지.
2. config.yaml: 모델 2개를 general-models / restricted-models 로 묶는다(✓ F&F 발췌 구조 그대로).
3. 키 발급: /key/generate 에 max_budget·budget_duration=1d(✓). 프로젝트는 team 으로 묶어 30d 예산(✓).
4. 승인 시연: restricted 모델 호출 → 차단 → 그룹 추가 → 같은 호출 성공(✓ F&F 가 실제 확인한 순서).
5. 차단 시연: 예산을 작게 잡고 호출을 반복해 80% 경고 → 100% 429 를 webhook 으로 받는다.
6. Claude Code 연결: ANTHROPIC_BASE_URL·ANTHROPIC_AUTH_TOKEN 두 줄(✓).

## ⑥ 내 과제에 옮길 때 체크리스트
- 귀속 기준을 새로 만들지 말 것. ✓ F&F 는 SSO 이메일(개인)과 svc:{서비스명}(서비스)을 그대로 썼다. 내 조직의 기존 식별자가 무엇인지 먼저 적는다.
- 외부 진입(Internal ALB)과 클러스터 내부 경로(ClusterIP)를 분리할 것. ✓ 같은 VPC 안 Pod 트래픽은 SNAT 가 없어 CIDR 제한에 걸린다.
- 전환 완료 판정은 200 응답이 아니라 세 가지(서비스 base_url·CloudTrail 직접 호출 0·게이트웨이 로그) ✓.
- 프록시가 닿는 비밀 목록을 미리 적어 둘 것(IAM 역할·제공자 키·DATABASE_URL ✓). 사고 시 교체 순서가 그 목록이다.

## ⑦ 내 데이터로 재는 방법 (제안)
데모는 수치를 보여주지 않는다. 독자가 자기 게이트웨이에서 다음 네 가지를 기록한다.
1. 키별 일 지출(spend API) — 차단 적용 전 1주 vs 후 1주.
2. 첫 주 429 발생 건수와 그중 "정당한 사용"이었던 비율(예산 보정 근거).
3. 키 요청 → 첫 성공 호출까지 걸린 분(F&F 비교점 3분 ✓).
4. 프롬프트 캐시 적중률(✓ F&F 대시보드 항목) — 비용 절감의 두 번째 레버.

출처
- https://aws.amazon.com/ko/blogs/tech/fnf-llm-gateway-on-amazon-bedrock/
- https://discuss.pytorch.kr/t/litellm-v1-107-0/12282
데모 repo: 이번 리허설에서는 제외(사용자 지시).

---

# 리허설 2 — 2026-10-10 ~ 10-16
## 숫자는 코드가, 해석은 LLM 이: 수치 대조 게이트가 붙은 데이터 분석 에이전트


표기: ✓ 그 주 검증 통과 카드·동결 원문의 사실 · 제안 = 우리 설계 · 미검증 = 출처 밖 지식 · 격리 = 일간 게이트가 QUARANTINE 한 카드(수치 인용 안 함)
선정: 씨앗 = Applied AI 2건(SD바이오센서·CJ올리브영) · 보강 = AI Agents 2건(Google 에이전트 평가·OECD) · 고려했으나 고르지 않음 = ShipStation·Orca·롯데백화점

## ① 어떤 문제인가
자연어로 운영 데이터를 묻는 에이전트를 프로토타입에서 프로덕션으로 올리면 세 가지가 깨진다. ✓ 같은 질문에 다른 답(재현성), 에이전트 사이를 오가며 늘어나는 지연·토큰, 문제가 났을 때 어디서 값이 달라졌는지 못 찾는 관측성. SD바이오센서가 겪은 그대로이고, ✓ CJ올리브영도 초기 구현에서 "응답이 느리고 같은 조건에서도 결론이 달라지는" 같은 문제를 만났다.

## ② 이번 주 근거
- ✓ SD바이오센서(AWS Korea Tech Blog, 10-16): 오케스트레이터 + 하위 에이전트 3개 → **단일 에이전트**로 단순화. 날짜 구간·계정 식별·통계 산출은 **버전 고정 순수 함수 도구**로 옮기고 입력 해시와 버전을 결과에 기록. 답변 생성 직후 **도구 실행 로그와 응답 수치를 대조하는 후처리 검증 게이트**(비침습 계층)를 두어 근거 없는 수치가 있으면 한 차례 재생성. 실행은 AgentCore Runtime(VPC 프라이빗, 세션 격리), 추적은 OpenTelemetry 기반 AgentCore Observability. 인용된 Anthropic 관찰: 멀티 에이전트가 단일보다 3~10배 토큰 소비.
- ✓ CJ올리브영(AWS Korea Tech Blog, 10-16): 인시던트 분석·데일리 헬스 체크 에이전트(Strands + AgentCore Runtime). **고객 피해 금액 계산과 지표 상태 판정은 코드, LLM 은 근거 해석만.** 전일 데이터만으로 판정하던 헬스 체크의 오탐을 **7일 기준선 + 최소 트래픽 기준 + 집계 미완료 날짜 제외**로 잡았다. 결과는 8개 영역 리포트와 Slack 알림.
- ✓ Google, Evaluating AI agents(10-15, AI Agents): 눈으로 보는 평가 대신 critical user journey 기준 골든셋, 단위 테스트·결정론 지표·LLM-as-judge·통합 테스트 4종 병행, 판정 루브릭은 1~5점 대신 **예/아니오 불리언**, 지연·토큰·비용·도구 호출 수를 함께 추적.
- ✓ OECD 25개 조직 인터뷰(10-12): 제한 없는 자율성으로 배포한 곳 없음, 되돌릴 수 없는 작업엔 사람 승인이 일반적.
- 「사실들을 엮으면」(제안): 같은 주에 한국 기업 둘이 서로 모르고 같은 결론에 닿았다. **결정론은 코드로, LLM 은 선택과 해석으로, 수치는 출력 단계에서 대조.** 데모의 주제는 이 패턴 하나다.
- 고려했으나 고르지 않음: ShipStation IT 헬프데스크(문의 97.5% 해결 ✓)·Orca Security(쿼리 비용 90% 절감 ✓)·롯데백화점(제안서 접수 160% 증가 ✓). 세 수치 모두 그 조직의 데이터·규모 위의 결과이고, 구조도 KB·9단계 파이프라인·WAF 등 소형 범위를 넘는다.

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 단일 에이전트 + 버전 고정 도구 카탈로그, 입력 정규화 → 해시 기록, 턴 종료 시 응답 수치 ↔ 도구 로그 대조 게이트 → 실패 시 1회 재생성, 결측 경고 문구, 7일 기준선 오탐 억제. ✓ 전부 두 글이 설계 결정으로 밝힌 것.
- 재현 안 됨(조직 결과): SD바이오센서의 데이터·도메인 도구, CJ올리브영의 Datadog 연동·보상안 규칙·시차 운영 맥락. 두 글은 정량 효과 수치를 내지 않았다(그래서 ⑦이 더 중요하다).

## ④ 아키텍처 (제안 — 두 사례를 한 패턴으로 소형화)
- 데이터: 로컬 SQLite 또는 RDS 소형 1개에 가짜 운영 테이블(주문·쿠폰·일별 지표).
- 에이전트: Strands 단일 에이전트, 모델은 Bedrock Claude. 역할 = 도구 선택 + 자연어 정리만.
- 도구 카탈로그(순수 함수, 버전 태그): date_range(), aggregate(), compare_to_baseline(7d). 각 결과에 input_hash·tool_version 포함.
- 출력 게이트(독립 계층, 제안): 답변의 모든 숫자를 추출 → 그 턴의 도구 로그에 값이 있는지 대조 → 없으면 도구 산출값을 다시 제시해 1회 재생성 → 또 실패면 QUARANTINE 표시로 반환. 데이터 부족 시 결측 안내 문구 강제.
- 실행: 로컬 → (선택) AgentCore Runtime. 관측: OpenTelemetry 트레이스에 input_hash·게이트 판정 기록.
- 되돌릴 수 없는 동작(보상 실행 등)은 데모에 넣지 않고 "승인 대기" 상태만 보여준다(OECD ✓).

## ⑤ 구현 순서 (제안)
1. 가짜 데이터 + 도구 3개를 먼저 만들고 단위 테스트로 결정론 확인(같은 입력 → 같은 해시·같은 출력).
2. 단일 에이전트 연결. 멀티 에이전트 비교판은 만들지 않는다 — 대신 ⑦에서 토큰을 잰다.
3. 출력 게이트: 숫자 추출 → 로그 대조 → 재생성 → QUARANTINE. 게이트는 에이전트 코드를 건드리지 않는 래퍼로(✓ 비침습).
4. 헬스 체크 모드: 전일 vs 7일 기준선, 최소 트래픽 미달·집계 미완료 날짜 제외(✓ CJ).
5. 평가 루프: 질문 20개 골든셋, 판정은 불리언 루브릭(✓ Google), 지연·토큰·도구 호출 수 기록.
6. (선택) AgentCore Runtime 배포 + Observability 연결.

## ⑥ 내 과제에 옮길 때 체크리스트
- 내 에이전트가 **직접 계산하는 숫자**가 무엇인지 목록으로 적는다. 그 목록이 도구 카탈로그다(✓ SD).
- 게이트는 **출력 단계에 붙이는 독립 계층**으로. 오케스트레이션을 고치지 말 것(✓ SD).
- 일별 판정은 하루 데이터로 하지 말 것. 기준선·최소 표본·집계 완료 여부 세 조건(✓ CJ).
- 멀티 에이전트가 필요한 세 조건(컨텍스트 오염 방지·병렬·전문화) 중 하나라도 뚜렷한가 자문한다. 아니면 단일(✓ SD 가 인용한 Anthropic 기준).
- 되돌릴 수 없는 동작엔 사람 승인(✓ OECD).

## ⑦ 내 데이터로 재는 방법 (제안)
두 글은 효과 수치를 주지 않았다. 독자가 자기 에이전트에서 다음을 잰다.
1. **근거 없는 수치 비율**: 답변 속 숫자 중 도구 로그에 없는 것의 비율 — 게이트 전/후.
2. **재현율**: 같은 질문 10회 반복 시 동일 답 비율 — 도구 이전 전/후.
3. **턴당 토큰·지연**: 단일 vs 기존 멀티(있다면). 비교점은 ✓ 3~10배(Anthropic 관찰).
4. **헬스 체크 오탐율**: 7일 기준선 적용 전/후 일주일.

## ⑧ 이번 주 모델로 바꿔 끼우면
- Grok 4.7 이 Bedrock 에 올라왔다(`xai.grok-4.7`, list-foundation-models 로 확인). 다만 관련 카드는 일간 게이트에서 **격리**됐으므로 그 글의 정답률 수치는 인용하지 않는다. 데모에서는 모델 id 하나만 바꿔 ⑦의 1·2·3을 다시 재는 용도.
- Reflection Beam(오픈 가중치, SageMaker JumpStart ✓)은 H100/H200 급 인스턴스가 필요해 이 데모 범위 밖. 주시.

출처
- https://aws.amazon.com/ko/blogs/tech/amazon-bedrock-agentcore-data-analysis-agent-sdbiosensor/
- https://aws.amazon.com/ko/blogs/tech/cj-oliveyoung-operations-agent-bedrock/
- https://developers.googleblog.com/evaluating-ai-agents-moving-past-the-vibe-check
- https://discuss.pytorch.kr/t/oecd-25-ai-pdf-36p/12148
데모 repo: 이번 리허설에서는 제외(사용자 지시).

---

# 리허설 3 — 2026-10-03 ~ 10-09
## 권한은 에이전트가 아니라 사용자의 것: 호출자 권한으로만 조회하는 Text-to-SQL 에이전트

표기: ✓ 그 주 검증 통과 카드·동결 원문의 사실 · 제안 = 우리 설계 · 미검증 = 출처 밖 지식
선정: 씨앗 = Applied AI 2건(GS에너지·경신홀딩스, 같은 날 AWS Korea Tech Blog) · 보강 = Applied AI 1건(Amazon Quick 실시간 ACL) + Safety 1건(Zenity AgentCorruption) + AI Agents 2건(DevOps Agent 자동 복구·Postman) · 고려했으나 고르지 않음 = Qlik·Cresta·Incarna 결제

## ① 어떤 문제인가
사내 데이터에 연결된 에이전트가 생기면 질문은 하나로 모인다. **에이전트가 사람보다 많은 데이터를 보게 되지 않는가.** ✓ GS에너지는 "에이전트는 호출한 사용자의 권한으로만 조회해야 하고, 그 판단은 별도의 에이전트용 권한 체계가 아니라 데이터 플랫폼의 거버넌스 규칙에서 나와야 한다"를 설계 과제로 적었다. ✓ 같은 주 Zenity 는 AgentCore 에서 공개 에이전트 하나에 보낸 메시지 한 통으로 같은 계정·리전의 모든 에이전트를 장악했다. 에이전트 간 격리가 없었고 기본 실행 역할이 계정 전체에 걸쳐 넓었다.

## ② 이번 주 근거
- ✓ GS에너지(10-06): SageMaker Unified Studio 를 카탈로그·거버넌스 허브로, AgentCore 를 런타임으로. 프로젝트(법인·조직 단위) 구독 → Lake Formation 접근제어 → Athena 조회. 카탈로그에서 **발견하는 권한과 값을 조회하는 권한을 구분**. 자산 73개·사용자 약 690명. 함정: 구독 승인과 실제 접근 권한 부여는 별개 단계.
- ✓ 경신홀딩스(10-06): LLM Gateway(EKS, Entra ID + Virtual Key — 개발자의 모델 호출 통제)와 **Agent Gateway(SSO + 턴 단위 토큰·도구 호출 기록 — 임직원의 에이전트 호출 통제)**를 분리. Text-to-SQL 은 Strands 단일 에이전트 + Skills 문서, Lambda MCP 도구 7종(list_databases … execute_query), **DB 는 읽기 전용 권한**. 초기 멀티 에이전트 → 단일 + Skills 로 바꾸자 실행 시간 172초→56초, 도구 호출 8회→1회. SAP 는 기존 REST 서버 경유, 비표준 인증은 Gateway Interceptor 로.
- ✓ Amazon Quick 실시간 ACL(10-07): 인덱스에 복제한 ACL 로 사전 필터(1단계) 뒤 **쿼리 시점에 원본(Google Drive 등) 권한을 사용자 토큰으로 재확인(2단계)**. 복제-필터 방식의 약점 셋 = AI 시스템은 권한의 원천이 아니다 · 동기화 사이의 공백 · 소스 권한 모델 변화. 회수된 권한이 며칠이 아니라 **몇 분** 안에 반영.
- ✓ Zenity AgentCorruption(10-08): 에이전트가 평문 요청에 IMDS 자격증명을 넘김, 기본 권한이 같은 계정·리전 전체 에이전트에 읽기·쓰기·삭제. AWS 는 IMDSv2 기본화·기본 역할 강화로 부분 수정, 연구자는 **에이전트별 최소 권한 역할을 직접 지정**하라고 권고.
- ✓ DevOps Agent 자동 복구(10-07): 복구 도구는 **승인된 Lambda allowlist 에서만**, 읽기 전용은 자동·변경은 사람 승인까지 Durable Functions 로 중단. ✓ Postman(10-09): 도구 40개 넘으면 선택 오류 증가 → 작업별 동적 노출, 상태 변경엔 사용자 승인.
- 「사실들을 엮으면」(제안): 같은 날 한국 기업 둘이 "데이터 권한은 플랫폼이, 에이전트는 그 권한을 빌릴 뿐"으로 갔고, 사흘 안에 AWS 는 쿼리 시점 재확인을, 보안 연구자는 넓은 기본 역할의 결과를 보여줬다. 데모 주제는 **호출자 권한 전파 + 조회 시점 재확인 + 에이전트별 최소 권한** 세 겹이다.
- 고려했으나 고르지 않음: Qlik(4만 고객·발견 10만 건 ✓)·Cresta(배포 시간 절반 ✓)·Incarna x402 결제(3일·200줄 ✓). 조직 결과이거나(Qlik·Cresta) 온체인 결제 인프라가 소형 범위를 넘는다(Incarna).

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 호출자 신원이 에이전트를 통과해 데이터 계층 권한으로 변환되는 경로, 읽기 전용 DB 권한, 도구 7종의 탐색→explain→execute 순서, 조회 결과에 대한 쿼리 시점 권한 재확인, 변경 작업 승인 대기, 에이전트별 전용 실행 역할. ✓ 전부 네 글이 설계 결정으로 밝힌 것.
- 재현 안 됨(조직 결과): 73개 자산·690명, 172→56초(그 조직의 스키마·질문 분포), Lake Formation·SMUS·Entra ID 전체 체계, 4만 고객. 독자 조직의 수치는 ⑦에서 직접 잰다.

## ④ 아키텍처 (제안 — 두 플랫폼의 권한 경로만 소형화)
- 신원: Cognito 사용자 풀 2계정(팀 A·팀 B) + 그룹 → 에이전트 호출 토큰에 그룹 클레임.
- 데이터: Postgres 1개(RDS 소형 또는 로컬), 테이블 3개에 **행 수준 보안(RLS)** — 팀 컬럼 기준. DB 계정은 읽기 전용(✓ 경신).
- 에이전트: Strands 단일 에이전트 + 도메인 Skills 문서 1개(✓ 경신). 도구 = list_tables / describe / sample_rows / explain / execute 5종 — 요청마다 **호출자 신원을 SET ROLE 로 DB 세션에 전파**해 RLS 가 걸리게 한다.
- 2단계 재확인(✓ Quick 구조를 축소): execute 결과를 돌려주기 전에 권한 서비스(작은 Lambda, 그룹→허용 테이블 맵)를 **쿼리 시점에 다시 조회**해 불허 테이블이 섞였으면 결과를 버리고 거부 사유만 반환. 권한 회수 → 다음 질문에서 즉시 반영되는지 보여준다.
- 실행 역할: 에이전트 1개당 IAM 역할 1개, 접근 자원 = 그 DB 시크릿 + 권한 Lambda 호출만(✓ Zenity 권고). IMDS 접근 차단.
- 변경 작업(UPDATE/DELETE)은 도구에 없다. 필요하면 "승인 대기" 큐로만(✓ DevOps Agent·Postman).

## ⑤ 구현 순서 (제안)
1. 데이터와 RLS 부터: 팀 A·B 행이 섞인 테이블, 읽기 전용 DB 사용자, RLS 정책. 에이전트 없이 psql 로 A/B 전환 확인.
2. 도구 5종을 Lambda(또는 로컬 MCP)로. execute 는 `explain` 통과한 SQL 만 받는다(✓ 경신 순서).
3. 신원 전파: 토큰의 그룹 → SET ROLE. 같은 질문을 A·B 로 던져 결과 행이 갈리는지 확인.
4. 2단계 재확인 Lambda 와 결과 필터. 권한 회수 후 첫 질문에서 거부되는 시간을 기록.
5. 에이전트별 최소 권한 역할 작성, IMDS 차단. 다른 에이전트의 시크릿을 읽어 보는 음성 테스트(실패해야 정상).
6. (선택) AgentCore Runtime + Gateway 로 올리고 턴 단위 도구 호출 기록(✓ 경신 Agent Gateway)을 Observability 로.

## ⑥ 내 과제에 옮길 때 체크리스트
- 권한 판정의 **원천이 어디인가** 적는다. 에이전트가 아니어야 한다(✓ GS·Quick).
- 발견 권한과 조회 권한을 구분했는가(✓ GS). 승인 표시와 실제 조회 가능이 별개일 수 있다(✓ GS 함정).
- 모델 호출 통제(개발자)와 에이전트 호출 통제(임직원)를 **다른 게이트웨이**로 나눌 것인가(✓ 경신).
- 에이전트 실행 역할이 **계정의 다른 에이전트 자원에 닿는가** 점검(✓ Zenity). 기본 역할을 그대로 쓰지 말 것.
- 변경 작업은 도구에서 빼고 승인 큐로(✓ DevOps Agent·Postman). 도구 수가 40개에 가까우면 작업별로 노출(✓ Postman).

## ⑦ 내 데이터로 재는 방법 (제안)
1. **교차 유출 0건**: 팀 A 질문 50개에 팀 B 행이 1건이라도 섞이면 실패. RLS 전/후, 2단계 재확인 전/후.
2. **회수 반영 시간**: 권한 회수 → 거부되기까지 분. 비교점 ✓ Quick "몇 분"(복제-필터는 동기화 주기).
3. **도구 호출 수·실행 시간**: 멀티 → 단일 + Skills 전/후. 비교점 ✓ 경신 8→1회, 172→56초(방향만).
4. **음성 테스트 통과율**: 다른 에이전트 시크릿·IMDS 접근 시도 N건 중 차단된 비율(목표 100%).

## ⑧ 이번 주 모델로 바꿔 끼우면
- ✓ Claude Haiku 5.5 가 10-07 Bedrock 에 올라왔다(`us.anthropic.claude-haiku-5-5` 등록 확인). Anthropic 은 Haiku 4.5 대비 비용 약 75% 절감, Opus 가 계획·Haiku 가 대량 실행 구성을 권한다. 이 데모에서는 도구 선택·SQL 생성을 Haiku 5.5 로 바꾸고 ⑦의 1·3 을 다시 잰다 — 권한 경로는 모델과 무관해야 하므로 **1 은 그대로 0건이어야 한다**(모델을 바꿔도 보안이 유지되는지가 이 절의 진짜 질문).
- Claude Opus 5.5·Sonnet 5.5 GovCloud(US) 제공(✓)은 규제 워크로드 독자에게만 해당. 주시.

출처
- https://aws.amazon.com/ko/blogs/tech/gs-energy-smus-agentcore/
- https://aws.amazon.com/ko/blogs/tech/ks-ax-ai-platform-with-bedrock-agentcore/
- https://aws.amazon.com/blogs/machine-learning/rethinking-access-control-for-rag-with-amazon-quick-and-amazon-bedrock/
- https://the-decoder.com/a-single-prompt-was-enough-to-hijack-every-ai-agent-in-an-aws-account-zenity-researchers-found/
데모 repo: 이번 리허설에서는 제외(사용자 지시).

---

# 리허설 4 — 2026-09-26 ~ 10-02
## "전부 확인했다"를 증명하는 에이전트: 구조화 추출 + 결정론 판정 + 완전성 영수증

표기: ✓ 그 주 검증 통과 카드·동결 원문의 사실 · 제안 = 우리 설계 · 미검증 = 출처 밖 지식
선정: 씨앗 = Applied AI 2건(Adjudicated Query 임대 계약 전수 점검 · 계약 인텔리전스 플랫폼, 둘 다 AWS ML Blog 참조 아키텍처) · 보강 = AI Agents 1건(앰비언트 에이전트 ask_human) + Applied AI 1건(Asana 권한 범위) · 고려했으나 고르지 않음 = Condé Nast·Barclays·Anthropic 영업 에이전트·클라우드 마이그레이션 에이전트

## ① 어떤 문제인가
RAG 챗봇은 계약 한 건의 지급 조건은 잘 찾지만, "250건 전체 계약 총액은?" "텍사스 임대 22,910건이 전부 새 법규에 맞는가?" 같은 **포트폴리오 전체 질문**에는 빠르고 자신 있게 틀린 답을 낸다. ✓ 상위 k개 청크만 보기 때문에 합산·개수·비교가 구조적으로 불가능하고, text-to-SQL 은 환각된 조건절이 모집단을 조용히 줄여도 숫자는 정확해 보인다. 규제·감사 영역에서는 "빠진 레코드가 없다"를 증명해야 한다.

## ② 이번 주 근거
- ✓ Adjudicated Query(AWS ML Blog, 10-02): 모델은 **자연어 → 고정된 타입 연산 호출 번역과 결과 설명 두 가지만** 한다. 쿼리를 쓰지 않고, 모집단을 정하지 않고, 판정하지 않는다. 판정은 결정론 규칙 엔진(규칙은 코드가 아니라 버전 관리되는 데이터, 연산자는 gte/lte/equals/exists). 모든 점검은 **완전성 영수증**(적합 + 위반 + 모호 + 판독불가 = 점검 대상)을 저장 전에 전산으로 입증. MCP 도구 정확히 6개, Lambda + Aurora Serverless v2, Bedrock 은 탐색 경로에서만 호출. 챗은 개수·영수증·표본만, 전체 행은 같은 저장소를 읽는 대시보드가.
- ✓ 계약 인텔리전스 플랫폼(AWS ML Blog, 09-29): **답은 더 나은 검색이 아니라 구조화 추출.** Claude Sonnet 4.6 추출 에이전트가 PDF 에서 8개 필드를 신뢰도 점수와 함께 추출 → Claude Haiku 4.5 **검증 에이전트가 독립 재확인** → 서명 여부 불일치는 Textract 가 최종 판정 → Aurora PostgreSQL 저장 → 집계는 DB 가. 단건 질문은 지식베이스로 그대로.
- ✓ 앰비언트 에이전트(AWS ML Blog, 10-01): S3·EventBridge·DynamoDB 스트림 이벤트가 프롬프트. `autoExecute` 기본 false → 작업은 Jobs 페이지에 대기, 사람이 검토 후 실행. 사람 개입은 `ask_human` 도구 하나로.
- ✓ Asana(Claude Blog, 09-29): 에이전트의 접근 권한은 그것을 실행시킨 사람의 범위로 제한.
- 「사실들을 엮으면」(제안): 사흘 간격으로 나온 두 참조 아키텍처가 같은 말을 한다. **LLM 은 비구조를 구조로 바꾸고 결과를 설명하되, 숫자와 판정은 결정론이 한다.** 앰비언트 패턴을 붙이면 "문서가 들어오면 추출 → 전수 점검 → 영수증 → 사람 승인"이 한 줄로 이어진다.
- 고려했으나 고르지 않음: Condé Nast(탐색 250분 → 2분 미만 ✓)·Barclays(1.6만 직원·100만 검색 ✓)·Anthropic 영업 에이전트(전환 2배 ✓)·마이그레이션 에이전트(IaC 3~4주 → 수 분 ✓). 전부 조직 결과이고, 14만 영상·은행 규모·Managed Agents 베타는 소형 범위를 넘는다.

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 고정 연산 6종 경계, 규칙 = 데이터, 완전성 영수증 불변식, 추출 → 독립 검증 → 제3 판정자 → DB, 집계는 SQL, 이벤트 → 대기 작업 → 승인. ✓ 두 글이 실행 가능한 샘플과 함께 공개한 설계.
- 재현 안 됨(조직 결과): 5만 건·22,910건 같은 규모, 주별 법규 룰북 내용, 250건 계약 포트폴리오의 실제 PDF. 두 글은 참조 아키텍처라 조직 효과 수치가 없다 — ⑦이 유일한 수치다.

## ④ 아키텍처 (제안 — 두 참조 아키텍처를 하나의 소형 파이프라인으로)
- 입력: S3 버킷에 가짜 계약 PDF 30건(필드 8개가 들어간 템플릿 생성).
- 추출: Bedrock 모델 A(Sonnet 급)가 8개 필드 + 신뢰도 → 모델 B(Haiku 급)가 **같은 PDF 만 보고** 독립 재추출 → 불일치 필드는 "모호"로 표기(✓ 계약 플랫폼 구조; Textract 제3 판정은 선택).
- 저장: Postgres 1개(RDS 소형 또는 로컬). 룰북 테이블(규칙 = 행: 필드·연산자·임계값·버전·시행일).
- 판정: 순수 함수 규칙 엔진. 결과 = 적합/위반/모호/판독불가 네 상태. **영수증 불변식을 저장 전에 assert**(✓). 합이 안 맞으면 run 은 끝나지 않는다.
- 대화 경계: MCP 도구 6종을 그대로 본뜬다(목록·점검 실행·영수증 조회·위반 표본·단건 상세·탐색 질의). LLM 은 질문 → 도구 호출 → 설명만(✓). SQL 생성 도구는 없다.
- 이벤트: PDF 업로드 → 작업 대기(autoExecute=false ✓) → 사람이 실행 → 영수증과 표본을 반환.
- 권한: 실행자 신원 범위로만 조회(✓ Asana). 실행 역할은 그 버킷·그 DB 만.

## ⑤ 구현 순서 (제안)
1. 룰북 + 규칙 엔진 + 영수증 assert 를 LLM 없이 먼저. 가짜 데이터로 "합이 맞지 않으면 실패"를 테스트로 고정.
2. 추출 A → 재추출 B → 불일치 = 모호. 신뢰도 임계값은 설정값으로.
3. MCP 도구 6종 Lambda(또는 로컬). execute_sweep 는 룰북 버전을 인자로 받고 결과에 기록.
4. 대화 에이전트 연결. 금지 테스트: "SQL 로 직접 세어 봐" 같은 요청에 도구가 없어 실패하는지 확인.
5. S3 이벤트 → 대기 작업 → 승인 실행. ask_human 은 "모호 N건을 사람이 볼까요?" 한 지점에만.
6. (선택) 대시보드는 같은 DB 를 읽는 Quick Sight 또는 간단한 테이블 뷰.

## ⑥ 내 과제에 옮길 때 체크리스트
- 내 질문 중 **전체를 세는 질문**이 있는가. 있으면 RAG 로는 못 한다(✓). 추출 → 구조화가 먼저.
- 판정 규칙을 **코드가 아니라 데이터**로 둘 수 있는가(✓). 법규·정책 변경이 배포가 아니라 행 편집이 되게.
- 결과 네 상태의 합이 대상 수와 같다는 **불변식을 어디서 assert** 하는가. 저장 전이어야 한다(✓).
- 추출 검증을 **같은 모델의 재질문이 아니라 다른 모델**이 하는가(✓ Sonnet → Haiku). 불일치 처리 규칙을 미리 정할 것.
- 자동 실행 기본값은 꺼 두고(✓ autoExecute=false), 사람 개입 지점을 도구 하나로 좁혔는가.

## ⑦ 내 데이터로 재는 방법 (제안)
1. **영수증 불일치율**: run 중 합이 안 맞아 중단된 비율(목표 0, 단 "조용히 빠진 0건"이 증명되는 것이 핵심).
2. **추출 불일치율**: 모델 A·B 가 다른 값을 낸 필드 비율 → 모호 큐 크기. 사람이 봐야 할 양을 정한다.
3. **RAG 대조**: 같은 전체 질문 20개를 RAG 챗봇과 이 파이프라인에 던져 정답률 비교(✓ 글이 말한 구조적 한계를 내 데이터로 확인).
4. **승인 대기 시간**: 이벤트 → 사람 실행까지 분. 자동 실행을 켤 근거가 되는 숫자.

## ⑧ 이번 주 모델로 바꿔 끼우면
- ✓ Claude Sonnet 5.5 가 Bedrock 에 올라왔다(09-28; `us.anthropic.claude-sonnet-5-5` 등록 확인). 추출 A 를 Sonnet 5.5 로, 검증 B 는 그대로 두고 ⑦의 2 를 다시 잰다 — 두 모델이 **달라야** 독립 검증이 유지된다.
- ✓ GPT-6.1 Sol 도 Bedrock 정식 출시(09-29; `us.openai.gpt-6.1-sol` 등록 확인). 검증 B 를 다른 계열로 바꾸면 cross-family 재확인이 된다. 선택.
- ✓ **서울 리전 in-region 추론**(09-30): 글은 Opus 5·Sonnet 5 를 말했고, 오늘 확인하면 서울 리전에 Opus 5.5·Sonnet 5.5 도 등록돼 있다. 데이터가 리전을 못 벗어나는 독자는 ④ 전체를 ap-northeast-2 에서 돌릴 수 있다. 크로스 리전 프로필이 없어 처리량은 리전 할당량에 묶인다(✓).

출처
- https://aws.amazon.com/blogs/machine-learning/sweep-thousands-of-leases-for-compliance-using-amazon-quick-and-the-adjudicated-query-pattern/
- https://aws.amazon.com/blogs/machine-learning/building-an-ai-powered-contract-intelligence-platform-with-amazon-quick-and-amazon-bedrock-agentcore/
- https://aws.amazon.com/blogs/machine-learning/building-ambient-agents-with-amazon-bedrock-agentcore-from-event-driven-signals-to-human-in-the-loop-workflows/
- https://www.anthropic.com/customers/asana (Claude Blog 카드 "Agents you can coach")
데모 repo: 이번 리허설에서는 제외(사용자 지시).

---

# 리허설 4-B — 2026-09-26 ~ 10-02 · 프론티어 기준 재작성
## 코치할 수 있는 에이전트: 자격증명은 금고에, 피드백은 역할별로, 행동은 모두가 보게

표기: ✓ 그 주 검증 통과 카드·동결 원문의 사실 · 제안 = 우리 설계 · 미검증 = 출처 밖 지식 · 확인 필요 = 가용성 등 출처에 없는 사실
선정(새 기준): 씨앗 = **Anthropic Claude Blog 3편**(Asana "Agents you can coach" 09-29 · "Managed Agents + NVIDIA OpenShell" 09-29 · "영업팀 인바운드를 Managed Agents 로" 09-30) · 보강 = Claude Code mods(Anthropic 10-01) · Google Skills 전환(10-01) · **AWS 층** = Claude Platform on AWS 다중 환경 접근(10-01) · 앰비언트 에이전트 ask_human(10-01)
4편(AWS 기준)과의 차이: 씨앗이 "AWS 참조 아키텍처"에서 "프론티어 랩이 자기 제품으로 보여준 운영 방식"으로. AWS 는 ⑤의 보강층.

## ① 어떤 문제인가
에이전트에 일을 맡기기 시작하면 세 질문이 바로 따라온다. **누가 이 에이전트를 가르치는가, 그것이 본 비밀은 어디에 있는가, 그것이 한 일을 누가 보는가.** ✓ Asana 는 "개인이 혼자 AI 와 주고받은 뒤 결과물만 공유하면 다른 사람은 프롬프트도 논의도 모른다"를 문제로 짚었고, ✓ Anthropic 영업팀은 월 수만 건 인바운드를 사람이 감당하지 못해 고객이 며칠을 기다리는 상황에서 출발했다.

## ② 이번 주 근거
- ✓ Asana(Claude Blog, 09-29): 에이전트는 사람과 같은 Work Graph 안에서 **역할**(콘텐츠 작성자·인사이트 분석가·PM …)로 존재하고, 프로필 페이지에 이름·용도·사용자·관리자·지침·스킬·연동·권한이 적힌다. **실효 권한은 그것을 실행시킨 사람의 권한에 묶인다.** 공유 메모리에 대한 피드백은 누구나 줄 수 있지만 **영구 반영·취소·삭제는 관리자·편집자만**, 나머지는 그 작업에만 적용. 에이전트는 연구 계획과 수행 단계를 활동 피드에 올려 접근 권한이 있는 모두가 읽고 댓글로 조정한다. 팀에 전문가 한두 명이 설정하면 나머지는 혜택만 받는다.
- ✓ Managed Agents + OpenShell(Claude Blog, 09-29): Managed Agents 는 **에이전트 루프를 샌드박스와 다른 서버에서** 돌리고, **자격증명은 별도 금고**에 두어 에이전트가 보지 못하게 하며, 감사 추적과 기존 접근 제어 연동을 제공. NVIDIA OpenShell(Apache 2.0)은 **규칙이 허용하지 않은 모든 행동을 차단**하고 도구·파일·네트워크·데이터 접근을 정책으로 강제, 모든 결정을 기록, 정책 증명기가 도달 범위를 수학적으로 증명. 좁은 권한으로 시작 → 로그 검토 → Claude 로 규칙을 조이는 순서를 권한다.
- ✓ 영업 인바운드(Claude Blog, 09-30): 구매 에이전트 = **프롬프트 하나 + 도구 몇 개 + Claude**, Managed Agents 가 호스팅·세션·도구 오케스트레이션. 엔지니어 1명이 몇 주. **영업·콘텐츠 리드가 Console 에서 시스템 프롬프트를 직접 편집**, 스테이징 에이전트에 먼저. **모든 변경이 버전**(내부 테스트 1주에 v7), 필요하면 이전 버전으로. 교훈: 규칙 목록보다 **목표 한 문장**, 프롬프트는 짧게, SME 를 개발 루프에.
- ✓ Claude Code mods(Anthropic, 10-01): 이벤트 전·후·대체·래핑에 끼는 TypeScript 함수, 샌드박스 없음(신뢰할 수 있는 소스만). ✓ Google 도 Gems 를 Skills 로 교체(10-01) — Skills 포맷은 Anthropic 발, 개방 표준.
- ✓ AWS 층 — Claude Platform on AWS(10-01): 전용 AI Services 계정에 구독·워크스페이스·API 키·cross-account 역할을 두고, 워크로드 계정은 역할을 assume 해 SigV4 로 호출, 개발자는 워크스페이스 범위 API 키, 외부 CI 는 OIDC 연합. ✓ 앰비언트 에이전트(10-01): ask_human 도구 하나, autoExecute 기본 false.
- 「사실들을 엮으면」(제안): 같은 주에 Anthropic 이 세 글로 한 그림을 그렸다. **에이전트 = 역할 + 금고 + 버전 + 피드. 가르치는 권한과 쓰는 권한을 나누고, 비밀은 에이전트 밖에, 변경은 버전으로, 행동은 모두가 본다.** 비개발자가 프롬프트를 고치는 Console 과 Asana 의 "편집자만 영구 메모리" 가 같은 원리다.
- 고려했으나 고르지 않음: 4편의 씨앗(Adjudicated Query·계약 인텔리전스)은 이번 판에서 "같은 주 AWS 참조 아키텍처" 한 줄로 내려간다. Condé Nast·Barclays 는 조직 결과.

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 역할 프로필(사용자·관리자·권한·스킬), 호출자 권한 상한, **역할별 메모리 쓰기 권한**(누구나 제안·편집자만 영구), 행동 피드 공개, 자격증명 금고 + 루프·샌드박스 분리, 거부-기본 정책 + 결정 로그, 프롬프트 버전과 롤백, 스테이징 → 프로덕션, ask_human 단일 개입점. ✓ 세 글이 설계로 밝힌 것.
- 재현 안 됨(조직 결과): 전환 2배·5일 단축·하루 수천 대화, Work Graph 전체, Notion·Rakuten 사례. **확인 필요:** Managed Agents 가 Claude Platform on AWS 에서 제공되는지 — 글은 "자체 인프라 또는 관리형 제공업체 샌드박스"라고만 썼다. ⑤ 는 두 경로를 다 둔다.

## ④ 아키텍처 (제안 — 세 글의 운영 원리를 한 에이전트에)
- 에이전트 1개, 역할 "제품 질문 응답자"(✓ Asana 의 Slack 반복 질문 → 작업 전환 예). 프롬프트는 목표 한 문장 + 지식 + 도구(✓ 영업 교훈).
- **자격증명 금고**: 에이전트 코드에 키 0개. 도구 호출은 금고가 대신 서명(Managed Agents 경로) 또는 AWS 경로에서는 AI Services 계정 cross-account 역할 + Secrets Manager(✓ CPonAWS 패턴).
- **거부-기본 정책**: OpenShell(또는 동등한 allowlist)로 도구·네트워크·파일을 규칙으로만 허용, 모든 결정 로그.
- **공유 메모리 2계층**: 제안 메모리(누구나, 그 작업에만) / 영구 메모리(편집자 역할만 커밋·취소·삭제) — 역할은 신원 공급자 그룹에서(✓ Asana 규칙).
- **버전**: 프롬프트·스킬·정책 변경마다 버전 번호, 스테이징 에이전트 먼저, 세션을 이전 버전으로 되돌릴 수 있게(✓ 영업).
- **행동 피드**: 계획·도구 호출·결과를 작업 스레드에 공개 게시, 댓글로 조정(✓ Asana).
- **개입점**: ask_human 하나(✓ 앰비언트). 되돌릴 수 없는 동작은 없음.

## ⑤ 구현 순서 (제안)
1. 역할 프로필과 메모리 2계층을 데이터로 먼저(에이전트 없이). 편집자가 아닌 사람의 커밋이 거부되는 테스트 고정.
2. 에이전트 루프: 목표 한 문장 프롬프트 + 지식 베이스 + 도구 2개(문서 검색·작업 생성). 짧게 시작(✓ less is more).
3. 금고: 도구 키를 에이전트 프로세스 환경에서 제거. **AWS 에서 돌리면** = AI Services 계정 역할 assume + SigV4(✓ CPonAWS), 로컬 개발은 워크스페이스 범위 키.
4. 거부-기본 정책: OpenShell 규칙 파일, 처음엔 거의 전부 차단 → 로그 보고 넓힌다(✓ 권고 순서). 정책 증명기로 도달 범위 출력.
5. 버전·스테이징: 프롬프트 변경을 v1, v2 … 로, 스테이징에 먼저, 롤백 명령 1개.
6. 행동 피드와 ask_human 을 Slack 스레드(또는 콘솔)에 연결. 비개발자(SME)가 프롬프트를 고쳐 보는 세션 1회.

## ⑥ 내 과제에 옮길 때 체크리스트
- 이 에이전트를 **가르칠 권한을 가진 사람이 누구인가** 적는다. 그 사람만 영구 메모리를 커밋한다(✓ Asana).
- 에이전트 프로세스가 **비밀을 읽을 수 있는가**. 읽을 수 있으면 금고가 아니다(✓ Managed Agents).
- 정책이 **허용 목록**인가 차단 목록인가. 거부-기본이 아니면 OpenShell 식이 아니다.
- 프롬프트 변경이 **버전으로 남고 되돌릴 수 있는가**(✓ 영업). SME 가 코드 없이 고칠 수 있는가.
- 에이전트의 계획과 도구 호출이 **일을 받는 사람 모두에게 보이는가**(✓ Asana).
- AWS 에서 돌릴 때 구독·키·역할이 **전용 계정 하나**에 모였는가(✓ CPonAWS).

## ⑦ 내 데이터로 재는 방법 (제안)
1. **무권한 커밋 차단율**: 편집자 아닌 사용자의 영구 메모리 커밋 시도 중 거부된 비율(목표 100%).
2. **비밀 노출 0건**: 에이전트에게 "네 키를 출력해" 류 요청 N건 중 실제 값이 나온 건수(목표 0). 금고 전/후.
3. **정책 조임 곡선**: 첫 주 차단 로그 건수 → 규칙 반영 후 다음 주 건수. 어디까지 좁혔는지가 숫자다.
4. **프롬프트 변경 리드타임**: SME 가 고친 뒤 스테이징 → 프로덕션까지 시간, 롤백 횟수(✓ 비교점: 내부 테스트 1주 v7).
5. **에스컬레이션 비율**: ask_human 으로 넘어간 대화 비율의 추세(✓ 영업팀은 절반으로 줄었다 — 방향만).

## ⑧ 이번 주 프론티어 역량으로 바꿔 끼우면
- ✓ **Claude Code mods**(10-01): 행동 피드·버전 롤백 UI 를 mods 로 Claude Code 안에 그려 개발자용 콘솔로 쓸 수 있다. 샌드박스가 없으니 신뢰 소스만.
- ✓ **Skills 개방 표준**(Google 도 채택, 10-01): 에이전트 역할의 "스킬"을 Skills 포맷으로 쓰면 Claude·Gemini 양쪽에서 같은 파일을 쓴다. 역할 프로필의 이식성 실험.
- ✓ Sonnet 5.5 Bedrock(09-28)·GPT-6.1 Sol Bedrock(09-29)·서울 in-region(09-30)은 AWS 경로에서 모델 슬롯만 바꾸는 변수. 보안 속성(⑦ 1·2)은 모델과 무관하게 유지돼야 한다.

출처
- https://claude.com/blog/agents-you-can-coach-how-asana-builds-human-agent-teams-with-claude
- https://claude.com/blog/giving-companies-more-control-over-their-ai-agents-with-nvidia
- https://claude.com/blog/how-anthropics-sales-team-rebuilt-inbound-with-claude-managed-agents
- https://claude.com/blog/claude-code-mods
- https://aws.amazon.com/blogs/machine-learning/implementing-multi-environment-access-for-claude-platform-on-aws/
데모 repo: 리허설에서는 제외(사용자 지시).

---

# 리허설 1-B — 2026-10-17 ~ 10-23 · 프론티어 기준 재작성
## 서브에이전트를 접어 넣기: 점진적 노출(skills + tool search)로 돌아가는 단일 루프, 그리고 그것을 재는 법

표기: ✓ 그 주 검증 통과 카드·동결 원문의 사실 · 제안 = 우리 설계 · 미검증 = 출처 밖 지식 · 확인 필요 = 가용성 등 출처에 없는 사실
선정: 씨앗 = **Anthropic "Building agents: When to fold subagents into your main agent loop"**(Claude Blog, 10-22) · 수렴 = Google "Architecting Governed, Self-Evolving AI Agents"(10-22) · Anthropic "Agent Skills 를 AAIF 에 기증"(10-22) · Google Agents CLI Extension System(10-21) · 보강 = Claude Cowork Enterprise(격리 VM·자격증명 샌드박스 밖, 10-23) · Claude Duet(사전 승인 행동 분류, 10-21) · Harness² 경량 구현(PyTorch KR, 비공식 — 비용 25배) · **AWS 층** = F&F LiteLLM 게이트웨이(예산·429), Bayer 감독 + 22 전문 에이전트(반례로) · 고려했으나 고르지 않음 = Claude Security(제품 발표)·Claude Platform on Google Cloud(가용성)·Agent Compute Engine(2차 보도)

## ① 어떤 문제인가
기업 에이전트는 흔히 이렇게 자란다. 의도 분류기 → 고정 다단계 파이프라인 → 사용자 세그먼트 분기 → 팀마다 서브에이전트 → 그 위에 오케스트레이터. ✓ Anthropic Applied AI 팀은 이 구조의 대부분이 "모델이 더는 대신해 줄 필요가 없는 일"을 하고 있었고, **명확한 시스템 프롬프트 하나 + 얇은 데이터 도구 4~5개 + 단단한 출력 가드레일**이 대부분을 덮더라고 썼다. 조직도를 복제한 에이전트 구조(Conway 의 법칙)가 문제다.

## ② 이번 주 근거
- ✓ Anthropic, When to fold subagents(10-22): 여러 기업 배포 비교에서 **skills 를 가진 단일 에이전트가 원샷 프롬프트 설계와 서브에이전트 설계 둘 다를 품질에서 자주 앞섰고, 비용·지연도 종종 낮았다.** 한 고객의 멀티에이전트 하네스 vs 단일 루프 평가는 단일이 약 2배 빠름. Claude Code 시스템 프롬프트를 고급 모델용으로 **80% 이상 감축**(skills·tools 점진적 노출 포함). 실패 유형: 컨텍스트 관리(핸드오프마다 유실), 서브에이전트 난립(소유자 없음), Frankenprompt(팀마다 한 문장씩), 지역 최적화된 평가, 지연. **서브에이전트가 여전히 맞는 경우 셋:** 컨텍스트 비대로 측정 가능한 성능 저하 / 버릴 수 있는 신선한 컨텍스트로 병렬 처리 / 도구 선택 실패·지침 충돌. 권고 단일 루프: 모델 하나·컨텍스트 창 하나·개방형 도구 루프, **하네스에 턴·비용 예산과 쓰기 게이트**, 매 턴 도구 호출 배치를 병렬 실행해 원시 결과를 같은 모델에 반환, 답 뒤 선택적 검증기. 중앙 팀 하나가 시스템 프롬프트와 품질을 소유. 마이그레이션 키트(목 시스템 데모 포함) 제공.
- ✓ Google, Governed Self-Evolving Agents(10-22, Project Chrysalis): 에이전트가 미들웨어 패치를 합성해 자가 수정·자가 비평·기억·**사람 승인 아래 멀티에이전트 구조를 재편**. 시뮬레이션 장애에서 최초 완화 15~45분 → 1.8초, 5xx 72.7~80% → 0%. Model Armor·KMS·Binary Authorization·OPA·이중 승인(HITL)으로 모든 자율 행동을 제약.
- ✓ Anthropic, Agent Skills 기증(10-22): 2025-12 공개 후 **70개+ 플랫폼 채택, 스킬 100만 개·설치 2.8억 건**, AAIF(리눅스 재단)로 이관. 점진적 노출의 "skills" 쪽이 개방 표준이 됐다.
- ✓ Google, Agents CLI Extension System(10-21): CLI 를 포크하지 않고 명령을 재정의·추가. 24개 명령 중 6개만 ADK 종속. 플랫폼 팀이 deploy 를 SBOM 스캔으로 감싸는 **거버넌스 정책을 확장으로 강제**하는 패턴.
- ✓ 보강 — Claude Cowork Enterprise(10-23): 세션마다 격리 VM, 기본 외부 네트워크 차단, **커넥터 자격증명은 샌드박스 밖**. Claude Duet(10-21): 메시지·결제·서명·삭제는 사전 승인, 증권 거래·계좌 이체는 승인 무관 금지 — 행동 등급표의 예. Harness²(PyTorch KR, 비공식 구현): 정답지 없이 하네스를 고쳐 35문항 중 5개를 새로 맞히고 회귀 0 이었지만 **비용이 단일 실행의 약 25배**.
- 「사실들을 엮으면」(제안): 같은 주에 Anthropic 은 "구조를 접어 모델에 넘겨라", Google 은 "구조를 에이전트가 스스로 고치되 승인 아래서"라고 썼다. 반대로 보이지만 둘 다 **하네스의 결정을 줄이고, 남는 결정은 예산·게이트·승인으로 묶는다**는 한 방향이다. Skills 표준화는 그 "접기"를 플랫폼 간 이식 가능하게 만든다.
- **AWS 층(같은 주):** ✓ Bayer 는 감독 에이전트 + 22개 전문 에이전트로 질문 80% 자체 해결(AgentCore·LangGraph) — Anthropic 의 세 예외(병렬·도구 선택·지침 충돌) 중 어디에 해당하는지 독자가 자기 사례로 판단할 반례. ✓ F&F 는 LiteLLM 게이트웨이의 일·월 예산과 429 로 "하네스의 비용 예산"을 모델 밖에서 강제한 예.
- 고려했으나 고르지 않음: Claude Security(제품 발표, 재현 대상 아님) · Claude Platform on Google Cloud(가용성 → ⑧) · Agent Compute Engine(2차 보도, 프리뷰 전).

## ③ 재현되는 것 vs 그 조직 고유의 것
- 재현됨(메커니즘): 단일 루프 설계(한 모델·한 컨텍스트·배치 도구 호출·병렬 실행·원시 결과 반환), skills 짧은 설명 → 필요 시 전체 로드, tool search 로 도구 점진적 노출, 턴·비용 예산, 쓰기 게이트, 답 뒤 검증기, 서브에이전트 보존 조건 셋의 **측정 기준**, 사전 승인 행동 등급, 자격증명 샌드박스 밖.
- 재현 안 됨(조직 결과): "약 2배 빠름", "80% 감축", Bayer 80%, Chrysalis 의 1.8초·0%(시뮬레이션). 전부 방향만. **확인 필요:** Anthropic 마이그레이션 키트의 공개 범위와 AWS 경로에서 tool search 동등 기능(아래 ⑤).

## ④ 아키텍처 (제안 — "접기 전/후"를 같은 과제에서 재는 소형 벤치)
- 과제: 고객 응대형 질의 30개(제품 정보·주문 조회·정책 질문 섞어 3 도메인). 목 데이터 도구 5개(✓ "얇은 데이터 도구 4~5개").
- **A 안(기존형)**: 의도 분류기 → 도메인 서브에이전트 3개 → 오케스트레이터 종합. 각 서브에이전트 자기 컨텍스트.
- **B 안(접은 형)**: 단일 루프. 시스템 프롬프트 1개(목표 + 출력 가드레일), skills 3개(도메인별 절차, 짧은 설명만 상주), 도구는 설명만 노출하고 필요 시 로드(tool search). 하네스에 **턴 예산·비용 예산·쓰기 게이트**. 답 뒤 선택적 검증기(결정론 체크 1개).
- 공통: 모든 도구 호출 로그, 턴마다 토큰·지연 기록, 자격증명은 루프 밖(✓ Cowork·Managed Agents 원리), 상태 변경 도구는 "승인 대기"만(✓ Duet 등급표).
- **접기 판정 규칙(✓ Anthropic 세 조건을 측정으로):** B 가 A 대비 (1) 품질 비열위 (2) 컨텍스트 비대로 품질이 꺾이는 구간 없음 (3) 도구 선택 오류율 상승 없음 → 접는다. 하나라도 깨지면 그 도메인만 서브에이전트로 남긴다.

## ⑤ 구현 순서 (제안) + "AWS 에서 돌리면"
1. 과제 30개와 정답(결정론 체크 가능한 것만)을 먼저. 평가는 **중앙 1개**(✓ 지역 최적화 평가 금지).
2. B 안부터 짓는다(단일 루프 + skills 3 + 도구 5). 예산·쓰기 게이트는 하네스 코드에.
3. A 안을 같은 도구로 짓는다(비교 대상이 공정하도록 도구·데이터 동일).
4. 30문항 × 각 3회 실행. 품질·토큰·지연·도구 선택 오류·핸드오프 횟수 기록.
5. 접기 판정 규칙 적용 → 도메인별 결론. "접지 못한 도메인"이 있으면 그 이유를 세 조건 중 하나로 적는다.
6. (선택) Chrysalis 식 자가 수정은 넣지 않는다 — 대신 Harness² 가 보인 25배 비용을 ⑦에서 상한선으로 적어 둔다.
- **AWS 에서 돌리면:** 모델 = Bedrock Claude Opus 5.5/Sonnet 5.5(✓ 등록). 루프 = Strands Agents 단일 에이전트, AgentCore Runtime(세션 격리). 도구 = AgentCore Gateway 로 MCP 노출. **확인 필요:** Gateway 의 의미 기반 tool search 가 "점진적 노출"의 동등물인지, Agent Skills 포맷을 Strands 에서 그대로 로드하는 공식 경로가 있는지. 비용 예산은 F&F 식 게이트웨이 예산(✓)으로 모델 밖에서 한 겹 더.

## ⑥ 내 과제에 옮길 때 체크리스트
- 내 에이전트 구조가 **조직도를 닮았는가**(✓). 팀 수 = 서브에이전트 수라면 의심.
- 서브에이전트를 남길 **세 조건 중 어디에 해당하는지 측정값**으로 말할 수 있는가(✓). 못 하면 접는 쪽이 기본.
- 시스템 프롬프트와 평가를 **한 팀이 소유**하는가(✓). 팀마다 한 문장씩 넣고 있다면 Frankenprompt.
- 하네스에 **턴·비용 예산과 쓰기 게이트**가 있는가(✓). 없으면 단일 루프는 위험하다.
- skills·도구가 **짧은 설명으로 상주하고 필요 시 로드**되는가(✓). 전부 상주면 접은 게 아니다.
- 되돌릴 수 없는 행동의 **등급표**가 있는가(✓ Duet). 자격증명이 루프 밖에 있는가(✓ Cowork).

## ⑦ 내 데이터로 재는 방법 (제안)
1. **품질 차(B − A)**: 결정론 체크 통과율. 비교점 ✓ "자주 앞섰다"(방향만).
2. **지연·토큰 비(B / A)**: 과제당. 비교점 ✓ 고객 사례 약 2배(방향만).
3. **컨텍스트 비대 꺾임점**: 한 세션에 과제를 누적할 때 품질이 떨어지기 시작하는 턴 수 — 세 조건 중 첫째의 측정.
4. **도구 선택 오류율**: 잘못된 도구 호출 / 전체 호출 — 세 조건 중 셋째의 측정.
5. **시스템 프롬프트 길이**: 접기 전/후 토큰. 비교점 ✓ 80% 감축(방향만).
6. **하네스 자가 수정 비용 상한**(선택): Harness² 비공식 구현의 약 25배를 "넘으면 중단" 기준으로.

## ⑧ 이번 주 프론티어 역량으로 바꿔 끼우면
- ✓ **Agent Skills 개방 표준(AAIF)**: B 안의 skills 3개를 표준 포맷으로 쓰면 Claude·ChatGPT·Cursor 등 70개+ 플랫폼에서 같은 파일. 이식성 실험.
- ✓ **Claude Platform on Google Cloud + Opus 5.5 Fast Mode**(10-23, 출력 최대 2.5배): 지연 비교(⑦ 2)를 Fast Mode 로 다시 재면 "하네스 단순화"와 "모델 속도" 효과를 분리할 수 있다.
- ✓ **Governed self-evolving(Chrysalis)**: 접기 판정을 사람이 아니라 에이전트가 제안하고 사람이 이중 승인하는 변형. 비용 상한(⑦ 6) 안에서만.
- 모델 슬롯(Opus 5.5·Sonnet 5.5·Fable 5.1 ✓ "thinking 끌 수 없음")은 변수. 바꿔도 **예산·게이트·승인 속성은 그대로**여야 한다.

출처
- https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop
- https://developers.googleblog.com/architecting-governed-self-evolving-ai-agents-on-gemini-agent-platform
- https://developers.googleblog.com/powering-the-agent-development-lifecycle-with-any-framework-from-adk-to-langchain-and-beyond
- Anthropic News "Donating Agent Skills to the Agentic AI Foundation"(10-22) · Claude Blog "Claude Cowork and chat come together for Enterprise"(10-23) · "Introducing Claude Duet"(10-21)
- AWS 층: https://aws.amazon.com/ko/blogs/tech/fnf-llm-gateway-on-amazon-bedrock/ · Bayer Crop Science ADE(AWS ML Blog, 10-17~23)
데모 repo: 리허설에서는 제외(사용자 지시).

---

# 리허설 1-B 축약판 (독자용 · 링크 주소 제외 2995자, 포함 3144자 · ④ 질문/측정 표 제거 후 · 2026-10-31 ③ 시작점(코드) 3줄 추가)

# 서브에이전트를 접어 넣기: 점진적 노출로 돌아가는 단일 루프
2026-10-17 ~ 10-23 · 이번 주 글: Anthropic "When to fold subagents" · Google "Governed Self-Evolving Agents" · Anthropic "Agent Skills 기증"

**데모 한 줄.** 같은 과제·같은 도구로 "분류기 + 서브에이전트" 안과 "단일 루프 + skills" 안을 나란히 돌려, 서브에이전트를 남길 세 조건을 측정값으로 판정한다.

## ① 어떤 문제인가
기업 에이전트는 흔히 이렇게 자란다. 의도 분류기 → 고정 파이프라인 → 세그먼트 분기 → 팀마다 서브에이전트 → 그 위에 오케스트레이터. Anthropic Applied AI 팀은 이 구조의 대부분이 "모델이 더는 대신해 줄 필요가 없는 일"을 하고 있었고, 명확한 시스템 프롬프트 하나 + 얇은 데이터 도구 4~5개 + 단단한 출력 가드레일이 대부분을 덮더라고 썼다. 조직도를 복제한 에이전트 구조가 문제다.

## ② 이번 주 근거
**Anthropic, When to fold subagents(10-22).** 여러 기업 배포 비교에서 skills 를 가진 단일 에이전트가 원샷 프롬프트 설계와 서브에이전트 설계 둘 다를 품질에서 자주 앞섰고 비용·지연도 종종 낮았다(조직 결과: 한 고객은 단일 루프가 약 2배 빠름, Claude Code 프롬프트는 80% 감축). 서브에이전트가 여전히 맞는 경우는 셋이다. 컨텍스트 비대로 측정 가능한 성능 저하, 버릴 수 있는 신선한 컨텍스트로 병렬 처리, 도구 선택 실패나 지침 충돌. 권고 루프는 모델 하나·컨텍스트 하나에 skills 와 도구를 짧은 설명만 상주시키고 필요할 때 로드하며, 턴·비용 예산과 쓰기 게이트는 하네스가 든다. 시스템 프롬프트와 평가는 중앙 팀 하나가 소유한다.

**Google, Governed Self-Evolving Agents(10-22).** 에이전트가 미들웨어 패치를 합성해 스스로 고치고, 멀티에이전트 구조 재편은 사람의 이중 승인 아래서만 한다. 자율 행동은 전부 정책 엔진과 승인에 묶였다(조직 결과: 시뮬레이션 장애의 최초 완화 15~45분 → 1.8초).

**Anthropic, Agent Skills 를 AAIF 에 기증(10-22).** 점진적 노출의 "skills" 쪽이 70개+ 플랫폼이 쓰는 개방 표준이 됐다(스킬 100만 개, 설치 2.8억 건).

**엮으면.** Anthropic 은 "구조를 접어 모델에 넘겨라", Google 은 "구조를 에이전트가 고치되 승인 아래서". 반대로 보이지만 둘 다 하네스의 결정을 줄이고 남는 결정을 예산·게이트·승인으로 묶는 한 방향이고, Skills 표준은 그 접기를 플랫폼 간에 옮길 수 있게 한다. 같은 주 AWS 사례도 양쪽에 있다. Bayer 는 감독 + 22개 전문 에이전트로 질문 80% 를 자체 해결했고(세 조건 중 어디인지 따져 볼 반례), F&F 는 LiteLLM 게이트웨이 예산과 429 로 비용 예산을 모델 밖에서 강제했다.

## ③ 데모 (제안): 접기 전/후 벤치
- 과제: 고객 응대 질의 30개(제품·주문·정책 3 도메인), 목 데이터 도구 5개.
- A 안(기존형): 의도 분류기 → 도메인 서브에이전트 3개 → 오케스트레이터. 각자 컨텍스트.
- B 안(접은 형): 단일 루프. 시스템 프롬프트 1개, skills 3개는 설명만 상주, 도구는 tool search 로 필요 시 로드, 하네스에 턴·비용 예산과 쓰기 게이트, 답 뒤 결정론 검증기 1개.
- 공통: 자격증명은 루프 밖(Claude Cowork 처럼), 상태 변경 도구는 승인 대기만(Claude Duet 처럼).
- 판정 규칙: B 가 A 대비 품질 비열위, 컨텍스트 누적에도 꺾임 없음, 도구 선택 오류 상승 없음 → 접는다. 하나라도 깨진 도메인만 서브에이전트로 남긴다.
- 순서: ① 과제 30개와 결정론 정답을 먼저, 평가는 중앙 1개 ② B 안 ③ 같은 도구로 A 안 ④ 30문항 × 3회, 품질·토큰·지연·도구 오류·핸드오프 기록.
- AWS 에서 돌리면: Bedrock Opus 5.5 / Sonnet 5.5 + Strands 단일 에이전트 + AgentCore Runtime, 도구는 Gateway. Gateway tool search 가 점진적 노출의 동등물인지는 확인 필요.
- 시작점(코드):
  - [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — examples/agents.py: AgentDefinition 으로 A 안 서브에이전트, 같은 SDK 로 B 안 단일 루프
  - [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks) — tool_use/tool_search_with_embeddings.ipynb(도구 필요 시 로드), skills/
  - [awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples) — Strands + Runtime + Gateway 예제(AWS 경로)
- 내 시스템에 대입: 팀 수와 서브에이전트 수가 같으면 이 벤치를 그대로 돌려 볼 것. 측정으로 세 조건을 말할 수 없으면 접는 쪽이 기본이다.

## ④ 이번 주 역량으로 바꿔 끼우면
- Agent Skills 표준 포맷으로 skills 3개를 쓰면 Claude·ChatGPT·Cursor 에서 같은 파일.
- Opus 5.5 Fast Mode(Google Cloud, 출력 최대 2.5배)로 지연을 다시 재면 하네스 단순화 효과와 모델 속도 효과를 분리할 수 있다.

출처
- https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop
- https://developers.googleblog.com/architecting-governed-self-evolving-ai-agents-on-gemini-agent-platform
- Anthropic News, Donating Agent Skills to the AAIF (10-22)

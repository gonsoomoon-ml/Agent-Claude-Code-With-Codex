# 7일치 카드 손분류 — 주제 밴드 재설계의 근거 (2026-10-24)

- **무엇:** 2026-10-17~10-23 run 7회, 관리자 계정 ledger 138행(같은 글 반복 6행 제외 = 고유 132편)을 **주제(무엇)** 와 **장르(어떤 종류)** 두 축으로 손분류(LLM 아님, 제목+발행처만). 결정 과정·7개 문제 토론은 `docs/superpowers/specs/2026-10-24-topic-grouping-design.md`.
- **골든셋:** 같은 라벨을 `scripts/area_eval/golden_7d.json` 에 기계 판독형으로 보존(source_id·card_key 포함 → card-cache 요약과 join 가능, 30일 TTL 주의).
- **체계 진화:** 헤드라인 5분야(Infra 칸 없음 → 카드 1/3 갈 곳 없음) → 6칸(+Infra & Platforms) → 7칸(Platforms & Production 분리) → **최종 6칸**(Applied AI = 플랫폼·운영 + 과학 응용 + 고객 사례; 플랫폼 '제공(availability)' 발표는 Models & Releases 로).

## 최종 6칸 분포 (고유 132편)

| 분야(메일 순서) | 편 | 비율 | 하루 평균 |
|---|---|---|---|
| AI Agents | 30 | 23% | 4.3 |
| Applied AI | 28 | 21% | 4.0 |
| Models & Releases | 28 | 21% | 4.0 |
| Inference & Hardware | 25 | 19% | 3.6 |
| Safety, Security & Policy | 12 | 9% | 1.7 |
| Industry & Business | 8 | 6% | 1.1 |
| 분류 불가 | 1 | 1% | 0.1 |

경계 사례(두 칸 동시 성립) 38/132 = 29% — 1차 체계 기준; 최종 체계는 '플랫폼 제공→Models & Releases' 규칙으로 최다 쌍(Models↔Industry)을 해소.

## 장르는 발행처가 거의 결정한다 (장르 밴드 = 발행처 밴드 복사본)

| 발행처 | 편 | 발표 | 가이드 | 사례 | 연구 | 보도 | 큐레이션 | 최다 장르 |
|---|---|---|---|---|---|---|---|---|
| AWS | 26 | 4 | 14 | 8 | 0 | 0 | 0 | 가이드 54% |
| Anthropic | 15 | 11 | 1 | 1 | 2 | 0 | 0 | 발표 73% |
| Google | 20 | 12 | 5 | 0 | 3 | 0 | 0 | 발표 60% |
| The Decoder | 32 | 0 | 0 | 0 | 0 | 32 | 0 | 보도 100% |
| Hugging Face | 16 | 8 | 3 | 0 | 5 | 0 | 0 | 발표 50% |
| PyTorch KR | 23 | 0 | 0 | 0 | 0 | 0 | 23 | 큐레이션 100% |

## 발행처 × 최종 분야 (주제는 발행처와 독립적)

| 발행처 | 편 | AI Agents | Applied AI | Models & Releases | Inference & Hardware | Safety, Security & Policy | Industry & Business | 최다 분야 비율 |
|---|---|---|---|---|---|---|---|---|
| AWS | 26 | 6 | 12 | 3 | 5 | 0 | 0 | 46% |
| Anthropic | 15 | 5 | 3 | 1 | 0 | 2 | 3 | 33% |
| Google | 20 | 3 | 5 | 5 | 5 | 0 | 2 | 25% |
| The Decoder | 32 | 5 | 4 | 11 | 1 | 8 | 3 | 34% |
| Hugging Face | 16 | 2 | 1 | 5 | 7 | 1 | 0 | 44% |
| PyTorch KR | 23 | 9 | 3 | 3 | 7 | 1 | 0 | 39% |

발행처를 알 때 맞히는 비율: **장르 76% · 주제 37%** → 장르 축은 새 정보가 거의 없고, 주제 축이 발행처와 가장 독립적이다.

## 날짜별 분포 (핵심 3 빼기 전)

| run | 편 | AI Agents | Applied AI | Models & Releases | Inference & Hardware | Safety, Security & Policy | Industry & Business | 빈 칸 | 1장 칸 |
|---|---|---|---|---|---|---|---|---|---|
| 10-17 | 10 | 1 | 3 | 3 | 1 | 2 | 0 | 1 | 2 |
| 10-18 | 11 | 5 | 1 | 1 | 1 | 1 | 2 | 0 | 4 |
| 10-19 | 17 | 3 | 4 | 3 | 4 | 0 | 3 | 1 | 0 |
| 10-20 | 26 | 5 | 4 | 8 | 8 | 1 | 0 | 1 | 1 |
| 10-21 | 21 | 5 | 4 | 3 | 3 | 2 | 3 | 0 | 0 |
| 10-22 | 23 | 7 | 5 | 5 | 4 | 2 | 0 | 1 | 0 |
| 10-23 | 24 | 4 | 7 | 5 | 4 | 4 | 0 | 1 | 0 |

## 분야별 기사 (고유 132편 · `*` = 경계 사례 · ⚠ = 격리 카드)


### AI Agents (30)

- 10-17 · AWS ML Blog · Building trust in AI agents: A production-ready evaluation framework with Amazon Bedrock A · _가이드_
- 10-18 · The Decoder · Four Gemini 4 Argon agents beat Minecraft without any human help · _보도_
- 10-18 · The Decoder · AI agents chasing a $465 train refund invented excuses, leaked medical data, and spammed a * · _보도_
- 10-18 · AWS Korea Tech Blog · AWS에서 AI 에이전트 실행 환경 격리하기 2부: Amazon EKS와 Agent Sandbox, 개념과 구성 * · _가이드_
- 10-18 · The Decoder · AI agents have bad taste in long-term decisions and a new benchmark proves it * · _보도_
- 10-18 · AWS Korea Tech Blog · AWS에서 AI 에이전트 실행 환경 격리하기 1부: Amazon EKS와 Agent Sandbox, 개념과 구성 · _가이드_
- 10-19 · PyTorch Korea 읽을거리 · Claudemy: 주제 하나로 웹을 조사해 출처가 달린 2분 오디오 강의를 만드는 Claude Code 스킬 · _큐레이션_
- 10-19 · Google Developers Blog · Step by Step guide: Build a Voice Agent That Never Goes Silent using ADK · _가이드_
- 10-19 · PyTorch Korea 읽을거리 · LeanREA: REA의 MCP 도구 207개 대신 8KB 스킬 파일 하나로 리버스 엔지니어링을 안내하는 에이전트 스킬 (≠ REA 공식 경량판) · _큐레이션_
- 10-20 · AWS ML Blog · Work management context for AI agents with Smartsheet MCP on AWS · _가이드_
- 10-20 · PyTorch Korea 읽을거리 · LLM 에이전트의 외부화(Externalization)에 대한 리뷰 논문 (2/2): 프로토콜과 하네스 엔지니어링, 남은 과제 · _큐레이션_
- 10-20 · PyTorch Korea 읽을거리 · [오픈소스] 하네스 논문 세 편을 에이전트 하나로 묶어 봤습니다: LongHarness + Harmony Harness + Harness² 경량 구현 (비공식) · _큐레이션_
- 10-20 · AWS ML Blog · ⚠ From data to decisions: Conversational supply chain intelligence with Amazon Quick and Ama · _가이드_
- 10-20 · Hugging Face Blog · ALTK-Evolve: How learned memory tops the τ²-bench leaderboard on customer service tasks wi · _연구_
- 10-21 · PyTorch Korea 읽을거리 · gitai: 한 브랜치에 몰린 코딩 에이전트들의 변경을 서버가 대신 rebase해 반영하는 Git 서버 (Anthropic Scion 설계 참고) · _큐레이션_
- 10-21 · Google Developers Blog · Powering the Agent Development Lifecycle with any framework, from ADK to LangChain and bey · _발표_
- 10-21 · Claude Blog · Claude Security now scans continuously and tracks fixes * · _발표_
- 10-21 · Claude Blog · Introducing Claude Duet * · _발표_
- 10-21 · PyTorch Korea 읽을거리 · Harness²: 정답 라벨 없이 작업마다 에이전트 하네스를 고치고, 그 경험을 다음 작업에 넘기는 프레임워크 (feat. Google) · _큐레이션_
- 10-22 · PyTorch Korea 읽을거리 · REAP: 리버스 엔지니어링 에이전트(REA)에서 바로 사용 가능한 55개의 리버스 엔지니어링 프롬프트 저장소 (≠ REA 공식) · _큐레이션_
- 10-22 · Claude Blog · Building agents: When to fold subagents into your main agent loop · _가이드_
- 10-22 · AWS Korea Tech Blog · 셀프 호스팅 Grafana 알림으로 AWS DevOps Agent의 인시던트 자동 조사 시작하기 · _가이드_
- 10-22 · Anthropic News · Donating Agent Skills to the Agentic AI Foundation * · _발표_
- 10-22 · The Decoder · Google's Agent Compute Engine gives every Gemini agent its own hardware-isolated micro vir * · _보도_
- 10-22 · Google Developers Blog · Architecting Governed, Self-Evolving AI Agents on the Gemini platform · _가이드_
- 10-22 · The Decoder · Anthropic takes on Grok Bot, Meta's Muse, and OpenAI's Dots with its always-on agent "Clau * · _보도_
- 10-23 · Claude Blog · Claude Cowork and chat come together for Enterprise * · _발표_
- 10-23 · PyTorch Korea 읽을거리 · AAIF에 Agent Skills, Open Responses, OpenEnv, OpenSandbox 합류해 프로젝트 10개로 · _큐레이션_
- 10-23 · PyTorch Korea 읽을거리 · whatsapp-mcp: 메시지 전송 없이 내 WhatsApp 대화를 AI 에이전트가 검색하게 하는 셀프 호스팅 MCP 서버 · _큐레이션_
- 10-23 · Hugging Face Blog · Turning Database Grading into RL Rewards: Post-Training Agents with ThinkingBox * · _연구_

### Applied AI (28)

- 10-17 · The Decoder · ⚠ Anthropics' Claude cracks a 25-year-old NSA cryptography mystery in under 30 minutes * · _보도_
- 10-17 · Claude Blog · ⚠ How an Anthropic Japan BDR runs his day with a fleet of Claude agents · _사례_
- 10-17 · The Decoder · Mathematicians say OpenAI doesn't understand its own Navier-Stokes proof · _보도_
- 10-18 · AWS Korea Tech Blog · Amazon Bedrock 기반 사내 LLM, 키 발급부터 비용 차단까지: F&F의 LiteLLM 게이트웨이 운영 사례 · _사례_
- 10-19 · PyTorch Korea 읽을거리 · [프로젝트 소개] APIGOTO: OpenAI Python SDK에서 base_url만 바꿔 여러 모델을 같은 코드로 비교하기 · _큐레이션_
- 10-19 · Google Cloud AI & ML · Who judges the judge? Three helpful ways to audit your LLM evaluators * · _가이드_
- 10-19 · AWS ML Blog · How Deepgram optimized voice AI at scale with AWS Trainium · _사례_
- 10-19 · Google Cloud AI & ML · Building full virtual vehicles on Google Cloud: From AAOS to the smallest MCU · _가이드_
- 10-20 · AWS ML Blog · How Octave built a secure multi-tenant AI foundation on Amazon Bedrock · _사례_
- 10-20 · Anthropic Research · How Claude designed protein binders against scorpion neurotoxins · _연구_
- 10-20 · PyTorch Korea 읽을거리 · Traceway: LLM 호출 비용까지 추적하고 AI 에이전트가 직접 조회하는 셀프 호스팅 관측 플랫폼 · _큐레이션_
- 10-20 · AWS Korea Tech Blog · AI 에이전트 시대의 기업 토큰 경제학: 비용 방정식으로 측정하고 Amazon Bedrock에서 줄이기 * · _가이드_
- 10-21 · AWS ML Blog · How U.S. Hunger connects leaders and data using Amazon Quick · _사례_
- 10-21 · Google Research · Empowering frontline maternal care with AI-assisted ultrasound · _연구_
- 10-21 · The Decoder · Claude Science tackles deadly scorpion stings by designing protein binders from scratch · _보도_
- 10-21 · AWS ML Blog · Beyond the KV cache: Training and serving i14’s Laplace 3B linear attention model on AWS T · _사례_
- 10-22 · AWS ML Blog · Deploy AI in a HIPAA-eligible environment with Amazon Quick · _가이드_
- 10-22 · Google DeepMind · Beyond tree cover: mapping the world’s forest types · _연구_
- 10-22 · The Decoder · Recursive shows first result of its AI-driven research process with Flint · _보도_
- 10-22 · PyTorch Korea 읽을거리 · PyMuPDF 2.0 릴리스: pip install 한 번으로 PDF → LLM용 마크다운까지 (3개 패키지 통합) · _큐레이션_
- 10-22 · AWS ML Blog · How IskayPet unified corporate knowledge with Amazon Bedrock Managed Knowledge Bases · _사례_
- 10-23 · Hugging Face Blog · LitPivot: Developing research ideas through dynamic contextualization within the literatur * · _연구_
- 10-23 · Anthropic News · Open call for guest investigators in the life sciences · _발표_
- 10-23 · AWS ML Blog · Visualize points and routes with GeoJSON in Amazon Quick Sight layer maps · _가이드_
- 10-23 · AWS ML Blog · Orchestrating SageMaker AI endpoint auto scaling with AWS CDK · _가이드_
- 10-23 · Google Research · Bringing foundational models to the front lines of TB screening · _연구_
- 10-23 · AWS ML Blog · How Bayer Crop Science built an agentic decision engine on Amazon Bedrock AgentCore with A · _사례_
- 10-23 · AWS Korea Tech Blog · W컨셉, AWS Transform과 Kiro로 .NET 10까지 대규모 현대화 여정 * · _사례_

### Models & Releases (28)

- 10-17 · The Decoder · Deepseek V4.1 Flash 1017 beats larger rivals in agentic tasks while once again massively c · _보도_
- 10-17 · PyTorch Korea 읽을거리 · MAI-Base-2 사전학습 레시피: Microsoft AI가 공개한, DeepSeek-V4-Pro-Base보다 4~12배 효율적이라는 2.8T MoE 모델의 사 * · _큐레이션_
- 10-17 · PyTorch Korea 읽을거리 · Meta, Mac Studio 두 대에서 돌아가는 816B 오픈 웨이트 모델 Muse Spark Open 공개 (feat. MLX) · _큐레이션_
- 10-18 · PyTorch Korea 읽을거리 · Bespoke Labs, 사실 하나만 바꾼 대조 데이터로 만든 9B 결정 모델 Nimble과 학습 레시피 공개 · _큐레이션_
- 10-19 · AWS ML Blog · Pegasus 1.5 from TwelveLabs is now available in Amazon Bedrock · _발표_
- 10-19 · The Decoder · Kling AI drops version 4.0 with stereo audio, multilingual lip sync, and a lighter Flash v · _보도_
- 10-19 · The Decoder · MiniMax M3.1 Flash shows China's AI price race has no floor in sight * · _보도_
- 10-20 · The Decoder · Mistral AI launches Voxtral 3, a full voice agent stack that listens, thinks, and talks in * · _보도_
- 10-20 · The Decoder · OpenAI says GPT-6 is much better with legacy programming languages such as COBOL and Fortr · _보도_
- 10-20 · Google Cloud AI & ML · Claude Opus 5.5 and Claude Sonnet 5.5 are now available in Google Antigravity · _발표_
- 10-20 · Hugging Face Blog · NVIDIA Cosmos3-H-Dreams: Bringing Clinical Surgery to Life Through Generative Simulation * · _발표_
- 10-20 · The Decoder · Elevenlabs releases two new speech-to-speech models designed for real-time AI conversation · _보도_
- 10-20 · AWS ML Blog · Access OpenAI GPT models on Amazon Bedrock from Canada with cross-Region inference * · _발표_
- 10-20 · The Decoder · Cloudflare's Clairic pulls data from documents faster and cheaper than LLMs * · _보도_
- 10-20 · Google Cloud AI & ML · Introducing Gemini for government services * · _발표_
- 10-21 · The Decoder · Google Cloud now offers OpenAI models alongside Gemini and Claude, becoming the only major * · _보도_
- 10-21 · Google Cloud AI & ML · Google Cloud expands model choice and flexibility, bringing OpenAI models to customers * · _발표_
- 10-21 · Hugging Face Blog · NVIDIA Kumo Relational Outperforms Supervised Machine Learning on Relational Data, No Trai * · _발표_
- 10-22 · Hugging Face Blog · Granite Speech 5.0: Transcribe, Translate, and Attribute more Accurately and Faster · _발표_
- 10-22 · Google Developers Blog · Streaming comes to API Gateway: real-time and AI-ready APIs, without changing your spec · _발표_
- 10-22 · AWS ML Blog · Amazon Polly delivers a major upgrade to its Generative engine · _발표_
- 10-22 · Hugging Face Blog · OlmoEarth v1.3: State-of-the-art embeddings for the whole planet * · _발표_
- 10-22 · Hugging Face Blog · Ensemble forecasting with IBM Granite time-series models * · _가이드_
- 10-23 · The Decoder · Chinese AI model Kimi K3.1 Pro is closing in on Anthropic's Claude Opus 5.5 · _보도_
- 10-23 · Google Cloud AI & ML · Expanding Claude availability and deployment choice on Google Cloud * · _발표_
- 10-23 · Claude Blog · Claude Platform is now available on Google Cloud * · _발표_
- 10-23 · The Decoder · Anthropic says its unreleased model is both more capable and better aligned than Mythos 5. · _보도_
- 10-23 · The Decoder · Canva launches Craft, its first in-house image model · _보도_

### Inference & Hardware (25)

- 10-17 · PyTorch Korea 읽을거리 · vLLM과 SGLang 중 무엇을 골라야 할까? Red Hat이 공개한 PagedAttention과 RadixAttention의 차이와 벤치마크 해석법 · _큐레이션_
- 10-18 · PyTorch Korea 읽을거리 · Pie: KV 캐시와 디코딩 루프를 사용자 프로그램에 맡기는 오픈소스 LLM 서빙 시스템 (feat. SOSP 2025) · _큐레이션_
- 10-19 · Hugging Face Blog · TorchNeuron: running HF models on AWS Trainium is easier than ever · _발표_
- 10-19 · AWS ML Blog · Push-based KV transfer to improve TTFT and TPOT for disaggregated inference in vLLM · _가이드_
- 10-19 · Google Developers Blog · Native Model Authoring for Edge with LiteRT Tensor API · _발표_
- 10-19 · AWS ML Blog · Improve TTFT for multi-turn agentic workloads with bi-directional KV transfer in vLLM · _가이드_
- 10-20 · PyTorch Korea 읽을거리 · Helion으로 고성능이면서 이식 가능한 vLLM 선형 백엔드 구축하기 | 파이토치 한국 사용자 모임 · _큐레이션_
- 10-20 · AWS ML Blog · Fine-tuning GPT-OSS-20B for multilingual reasoning on Amazon SageMaker HyperPod · _가이드_
- 10-20 · Hugging Face Blog · AnyLanguageModel 1.0: One Year of Local Models on Apple Platforms · _발표_
- 10-20 · Hugging Face Blog · Hugging Face ❤️ TorchTPU: TPUs, Natively · _발표_
- 10-20 · Google Developers Blog · Bringing Visual Graph Debugging to Custom Edge Compilers with Model Explorer · _발표_
- 10-20 · Google Developers Blog · Unifying Edge AI: How Coral NPU’s open standard brings portable, energy-viable intelligenc · _발표_
- 10-20 · Google Developers Blog · Integrating TorchTPU into TorchTitan and Optimizing Models for TPU · _가이드_
- 10-20 · Google Developers Blog · Announcing New vLLM and SGLang Inference Engines on TPU · _발표_
- 10-21 · The Decoder · Nvidia's DSX POD could cut AI data center setup from six months to as little as 14 days * · _보도_
- 10-21 · Hugging Face Blog · How Specializing the Vocabulary of SLMs Can Cut Inference Cost by 77% in Real Applications · _연구_
- 10-21 · Hugging Face Blog · MPS in PyTorch 2.15 · _발표_
- 10-22 · PyTorch Korea 읽을거리 · 다음 주 출시되는 PyTorch 2.15부터 Mac GPU 지원 강화: MPS 백엔드의 FP8 지원 및 MoE 디코딩 5~6.5배 향상 등 · _큐레이션_
- 10-22 · PyTorch Korea 읽을거리 · DeepInfer: DeepSeek이 V4.1-Flash 모델의 서비스에 사용하는 추론 프레임워크 (단, 오프라인 추론만 공개 😅) · _큐레이션_
- 10-22 · Hugging Face Blog · Profiling TorchNeuron (Part 1): System-level profiling on AWS Trainium. · _가이드_
- 10-22 · AWS ML Blog · Write your own training loop — without managing GPUs — with Amazon SageMaker training sess · _발표_
- 10-23 · AWS ML Blog · Multi-Turn Reinforcement Learning on Amazon SageMaker AI: A hands-on guide · _가이드_
- 10-23 · PyTorch Korea 읽을거리 · Modular의 Mojo와 MAX: CUDA 종속 없이 여러 AI 하드웨어를 같은 코드로 다루려는 언어와 추론 프레임워크 · _큐레이션_
- 10-23 · PyTorch Korea 읽을거리 · AWS, Trainium을 CUDA처럼 PyTorch 장치로 쓰는 네이티브 백엔드 TorchNeuron 공개 (feat. Hugging Face) · _큐레이션_
- 10-23 · Hugging Face Blog · Does Your Model Run on AWS Trainium? Look It Up · _가이드_

### Safety, Security & Policy (12)

- 10-17 · The Decoder · An OpenAI model hacked a government site, grabbed 24 years of hospital data and kept it qu · _보도_
- 10-17 · The Decoder · AI models hide mistakes in their own work reports, but one sentence in your prompt can hel * · _보도_
- 10-18 · The Decoder · Two German courts now hold Google liable for what its AI overviews say · _보도_
- 10-20 · Hugging Face Blog · FairStress: A deeper evaluation of fairness in LLM decision-making * · _연구_
- 10-21 · The Decoder · OpenAI can't yet explain why its coding agents switch off misalignment monitoring * · _보도_
- 10-21 · The Decoder · OpenAI's GPT-5.6 Sol and Google's Gemini 4 Argon found critical PHP flaw affecting million · _보도_
- 10-22 · The Decoder · Major US banks are locking out AI agents that log in with customer credentials * · _보도_
- 10-22 · The Decoder · An AI agent in "Skynet mode" hijacks unprotected language models to launch self-sustaining · _보도_
- 10-23 · Anthropic Research · An alignment assessment of the UK AISI cybertesting incident * · _연구_
- 10-23 · The Decoder · Three-week on-site audit at OpenAI reveals major gaps in AI safety monitoring · _보도_
- 10-23 · PyTorch Korea 읽을거리 · LiteLLM v1.107.0 공급망 공격: 정식 릴리스 파이프라인이 서명해 배포한 악성 패키지 · _큐레이션_
- 10-23 · Claude Blog · Claude Duet Safety, Privacy, and Security * · _발표_

### Industry & Business (8)

- 10-18 · Anthropic News · Investing in the public benefit * · _발표_
- 10-18 · The Decoder · Anthropic has nearly stopped hiring junior staff because AI agents now work six times as m · _보도_
- 10-19 · Google Cloud AI & ML · Google named a Leader in the 2026 IDC MarketScape for Agentic AI Platforms · _발표_
- 10-19 · The Decoder · The neocloud shakeout is coming, and Nvidia has the most to lose · _보도_
- 10-19 · The Decoder · Stripe says AI agent purchases are adding up, but it won't share the numbers * · _보도_
- 10-21 · Claude Blog · HCLTech becomes a Global Premier Partner for Claude · _발표_
- 10-21 · Google AI (The Keyword) · Southeast Asia’s digital economy to hit $368 billion · _발표_
- 10-21 · Anthropic News · Physicist Christopher Stubbs joins Anthropic's Long-Term Benefit Trust · _발표_

### 분류 불가 (1)

- 10-21 · Anthropic News · Announcements · _발표_

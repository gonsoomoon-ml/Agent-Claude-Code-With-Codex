# Haiku LLM-as-Judge 관련성 필터 (relevance judge) — 설계

- **상태:** DRAFT (2026-07-10)
- **작성:** brainstorming → 이 spec → 구현(TDD)
- **관련 인시던트:** aws-kr-tech 소스에서 비-AI 기사("04 Oracle Database@AWS 네트워크 구성 가이드")가 이메일로 발송됨.

## 1. 배경 / 문제 (root cause, 재현 확정)

`require_ai` 소스(종합 피드)는 curate 단계에서 `is_ai_relevant()` 키워드 필터로 비-AI 기사를 컷한다(요약·검증 *전* 비용 절감). 그러나 이 필터는 **recall 우선 + 8000자 본문 부분일치**라, 본문 어딘가에 광의 키워드가 한 번만 스쳐도 통과한다.

- 재현 결과: Oracle 기사의 유일한 매칭 키워드는 `데이터센터`(영문 매칭 0·다른 한글 0). Oracle DB 네트워크 가이드가 "데이터센터"를 언급하는 건 당연하지만 데이터센터는 AI 신호가 아니라 범용 인프라 용어다.
- 이번이 키워드 필터 **오탐 2번째 수정**이다(1번=aitimes 푸터 "Powered by AItimes AI Solution"의 'AI' 함정, `_FOOTER_RE`로 이미 패치). "고칠 때마다 다른 자리에서 새 오탐"은 **아키텍처가 벽에 닿은 신호** — 키워드 부분일치는 구조적으로 샌다.
- 부수 문제(누락/false negative): `\bAI\b` 정규식은 한글 조사가 붙은 "AI가"·"AI를"을 못 잡고, 키워드 없이 명백히 AI인 기사(예: 코딩 코파일럿류)를 떨군다.

## 2. 결정 (사용자 확정)

1. **Haiku LLM-as-Judge로 대체.** 키워드 필터(`is_ai_relevant`)는 **폴백**으로 남긴다(LLM 오류 시 안전망 + 테스트 결정론 기본값).
2. **전 `require_ai` 소스에 한 번에 적용**: `aitimes` · `aws-kr-tech` · `google-dev`.
3. spec 작성 후 구현.

## 3. 왜 이게 신뢰 속성을 안 깨나 (decorrelation 무관 — 비협상 확인)

이 필터는 **verify-before-publish 게이트가 아니라 그 상류의 사전 필터**다.

- relevance 판정은 **주장(claim)이 아니며 certifier에게 넘어가는 증거도 아니다.** Haiku가 "AI 기사다"라고 골라도, author는 여전히 백지에서 요약하고 **certifier(codex)는 여전히 동결 바이트에서 독립 재도출**한다 — 두 모델 오류가 상관될 지점이 없다.
- "Codex 빼면 붕괴하는 중심 속성"은 그대로. relevance는 그 속성 **바깥의 비용 최적화 컷**.
- inclusion test의 "얇은 LLM 분류기 래퍼 금지"는 **제품 코어**에 대한 제약이지 내부 부품엔 적용 안 됨.

## 4. 목표 / 비목표

**목표**
- 종합 피드에서 비-AI 기사를 의미 기반으로 컷(정밀도↑) + 조사 경계·무키워드 AI 기사도 포착(recall↑).
- 기존 208 테스트 결정론 **무변경 유지**(seam 기본값=키워드).
- AWS-free 로컬 baseline(`local.run`)·스모크는 **네트워크 호출 없이** 그대로 동작.
- 새 파이썬 의존성 **0**, 새 IAM 권한 **0**(검증됨 — 아래 §8).

**비목표(YAGNI / 미래)**
- 판정 verdict의 **cross-run 영속 캐시**(content-hash 키). v1은 union-fetch가 이미 run 내 소스 dedup을 하므로 run당 기사 1회 판정으로 충분. 영속 캐시는 후속.
- 키워드 필터 **완전 삭제**(폴백으로 유지).
- author/certifier/gate/render **불변**(decorrelation·trust 경계 미접촉).
- `supervisor.py`(옵션 Strands 경로)는 §7에서 부차 배선만.

## 5. 설계

### 5.1 relevance 계층 (core/retrieval/relevance.py)

```
keyword_relevance(title, text) -> bool     # = 현재 is_ai_relevant (이름 유지, 폴백·기본값·테스트용)
llm_relevance(title, text, *, invoke) -> bool
    # Haiku 분류. invoke = (system, user) -> str 형태의 얇은 호출 시임(테스트 fake 주입).
    # 예외/파스 불가 시 → keyword_relevance 로 폴백 + _debug.warn (non-silent).
RelevanceFn = Callable[[str, str], bool]
```

- 프롬프트(고정·결정론): system = *"You are a strict classifier. Decide whether a news article is about artificial intelligence (AI/ML/LLMs, AI hardware such as GPUs/NPUs/semiconductors-for-AI, or the AI industry/companies). Answer with exactly one word: YES or NO."* user = `제목 + 본문[:1500]`(리드로 충분·저비용).
- 파싱: 응답 대문자에 `YES`면 True, `NO`면 False, 그 외(빈/모호) → `keyword_relevance` 폴백.
- 옵션(호출 파라미터): `max_tokens≈8`, `temperature=0`(Haiku 4.5는 sampling 허용), thinking off(기본).

### 5.2 Bedrock 호출 (core/retrieval/relevance_bedrock.py — boto3만)

- `make_bedrock_relevance(settings) -> RelevanceFn`: lazy `boto3.client("bedrock-runtime", region_name=settings.region)`를 클로저에 담아 `llm_relevance`를 부분 적용해 돌려준다.
- 본문 = Anthropic Messages API(Bedrock) JSON: `{"anthropic_version":"bedrock-2023-05-31","max_tokens":8,"temperature":0,"system":...,"messages":[{"role":"user","content":...}]}`; `invoke_model(modelId=settings.relevance_model_id, body=...)` → `json.loads(resp["body"].read())["content"][0]["text"]`.
- **모든 예외**(throttle/timeout/파스) 삼켜서 `keyword_relevance`로 폴백 + `_debug.warn("relevance llm", ...)`. author 카드-격리 인시던트 교훈대로 한 소스/한 기사 실패가 전체를 죽이면 안 됨.

### 5.3 curate seam (core/retrieval/curation.py)

- 시그니처: `curate(..., relevance_fn: RelevanceFn | None = None)`.
- 기본값: `relevance_fn = relevance_fn or keyword_relevance` → **주입 없으면 키워드**(테스트·로컬 무변경).
- line 56: `if source.require_ai and not relevance_fn(art.title, art.raw_text):` 로 교체.

### 5.4 pipeline seam (core/pipeline.py)

- `run_briefing(..., relevance_fn: RelevanceFn | None = None)` 추가 → `curate(..., relevance_fn=relevance_fn)`로 전달.

### 5.5 config (core/config.py)

- `Settings`에 추가:
  - `relevance_model_id: str` — 기본 `global.anthropic.claude-haiku-4-5`(author의 `global.anthropic.claude-sonnet-4-6` 컨벤션 미러; 정확한 inference-profile id는 배포 시 확인).
  - `relevance_llm_enabled: bool` — env `RELEVANCE_LLM_ENABLED`(기본 **off**). deploy_runtime가 런타임 env에 `"1"` 주입(= `CLAUDE_CODE_USE_BEDROCK` 패턴). 로컬/테스트는 off → 키워드.

### 5.6 데이터센터 정리(hygiene)

키워드 필터가 이제 **폴백**이므로, 폴백도 깨끗하게: `_KO_KEYWORDS`에서 `데이터센터` 제거(입증된 오탐원, Oracle 재현으로 부수 피해 0 확인). `반도체`는 유지(AI 칩 문맥 신호로 aitimes에 유용) — LLM이 주 판정자라 리스크 낮음.

## 6. 배선 (production)

`agentcore_runtime.py`(어댑터, settings 보유)가 판정 함수를 만들어 `run_briefing`에 주입:

```
relevance_fn = make_bedrock_relevance(settings) if settings.relevance_llm_enabled else None
run_briefing(..., relevance_fn=relevance_fn)
```

- `local.run`(AWS-free): 미주입 → 키워드. AWS-free 유지.
- 테스트: 미주입 → 키워드. 결정론 유지.

## 7. supervisor.py (부차)

옵션 Strands 경로도 동형 seam: `_CTX["relevance_fn"]`을 `run_supervisor`가 settings에서 세팅 → `curate_sources`가 `curate(..., relevance_fn=_CTX.get("relevance_fn"))`. 기본 프로덕션 경로 아니므로 후순위.

## 8. 배포 / IAM / 비용

- **IAM:** 변경 불필요. `deploy_runtime.py`의 `BedrockInvokeAuthor`가 이미 `bedrock:InvokeModel`을 `foundation-model/*` + `inference-profile/*`에 부여(검증됨).
- **의존성:** 변경 불필요. boto3(이미 `>=1.35`)만 사용.
- **env:** `deploy_runtime.py` 런타임 env dict에 `"RELEVANCE_LLM_ENABLED":"1"` 추가(그리고 원하면 `RELEVANCE_MODEL_ID`).
- **비용:** ~$0.004/건(제목+리드 ~2K in + ~8 out, Haiku $1/$5 per 1M) × ~10–30건/일 ≈ **~$0.1/일, 월 $3–4**. 비싼 author/certifier(~$0.10+/건) 사이클을 오탐 하나당 하나씩 절감 → 순이득.
- **풋건 주의(메모리):** `deploy_scheduler` 재실행이 `BRIEFING_DRY_RUN=1`로 리셋됨(복원 필수). 이번 변경은 runtime 배포라 무관하지만, 소스/런타임 재배포 시 `deploy_api`+`deploy_runtime` 둘 다.

## 9. 테스트 계획 (TDD)

1. **회귀(무변경):** 기존 relevance/curate 테스트 — seam 기본값=키워드라 그대로 green.
2. **llm_relevance(파스):** fake `invoke`가 `"YES"`/`"no"`/빈문자/`"maybe"` 반환 → True/False/폴백/폴백. `invoke`가 raise → 키워드 폴백 + warn.
3. **make_bedrock_relevance:** fake boto3 client(monkeypatch)로 body 조립·응답 파싱 검증(네트워크 없음).
4. **curate seam:** 주입 fake relevance_fn이 특정 기사 drop/keep 하는지 + `require_ai=False` 소스는 미호출.
5. **Oracle 회귀:** fake 판정자가 Oracle 기사에 False → drop; 키워드 폴백은 (데이터센터 제거 후) 여전히 drop → 두 계층 모두 고쳐짐을 문서화.
6. **데이터센터:** `keyword_relevance("...데이터센터...")`가 이제 False(제거 확인), `반도체`는 True 유지.

## 10. 검증 (verify-before-completion)

- `uv run ruff check src tests` · `uv run pytest`(회귀 green + 신규).
- 실 e2e: 배포 후 `DEBUG=1 uv run python scripts/e2e_smoke.py` 또는 trial 발송으로 aws-kr-tech에 Oracle류가 안 뜨는지 라이브 확인.

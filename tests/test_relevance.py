"""relevance — broad(종합지) 소스용 AI 키워드 필터(결정론·recall 우선) + Haiku LLM-as-Judge."""
from briefing.core.retrieval.relevance import is_ai_relevant, llm_relevance


def test_keeps_ai_articles():
    assert is_ai_relevant("코리아스타트업포럼, '피지컬 AI 산업협의회' 출범")          # AI 토큰
    assert is_ai_relevant("딥시크, 추론 속도 85%↑ 'DSpark' 오픈소스 공개")           # 딥시크
    assert is_ai_relevant("팩트챗 슈퍼 에이전트…클로드, 챗GPT 점유율 첫 역전")          # 클로드·에이전트
    assert is_ai_relevant("RBC 조사", "기업의 AI·LLM 예산이 생산 단계로 진입")          # 발췌에만 있어도 keep


def test_drops_non_ai_articles():
    assert not is_ai_relevant("여수세계섬박람회 현장 점검…구 국도 17호선 30억 지원 건의")
    assert not is_ai_relevant("순천시, 100kW 규모 영농형 태양광 실증단지 본격 가동")
    assert not is_ai_relevant("목포문화예술회관, 7월 18일 가족극 '똥벼락' 공연 개최")


def test_word_boundary_avoids_english_false_positives():
    assert not is_ai_relevant("Shanghai expo opens next week")   # 'AI' in Shanghai → no match
    assert not is_ai_relevant("email marketing tips for 2026")   # 'ai' in email → no match


def test_strips_media_boilerplate_footer():
    # 매체 푸터의 'AI'(aitimes 발췌 끝의 "Powered by AItimes AI Solution")가 비-AI 기사를 통과시키면 안 됨
    body = "여수시는 박람회 준비 현장을 점검했다.\n주영효 기자 society@aitimes.com\nPowered by AItimes AI Solution"
    assert not is_ai_relevant("여수세계섬박람회 현장 점검", body)
    # 본문에 진짜 AI 신호가 있으면 푸터 제거 후에도 keep
    assert is_ai_relevant("메모리 대란", "AI 데이터센터 수요로 메모리값 급등.\nPowered by AItimes AI Solution")


# ── 키워드 폴백 위생: '데이터센터' 제거(Oracle 오탐원), '반도체' 유지 ──────────────────
def test_datacenter_no_longer_ai_signal():
    # Oracle DB 네트워크 가이드가 통과한 유일한 이유 = '데이터센터'. 이제 폴백에서도 안 통과.
    assert not is_ai_relevant("Oracle Database@AWS 네트워크 구성 가이드", "신규 데이터센터 리전에 배치한다")


def test_semiconductor_still_ai_signal():
    # '반도체'는 AI 칩 문맥 신호로 유지(aitimes 종합 피드).
    assert is_ai_relevant("차세대 반도체", "차세대 반도체 공정 로드맵 발표")


# ── llm_relevance: 결정론 파싱 + 폴백(장애·모호 → 키워드) ─────────────────────────
def test_llm_relevance_parses_yes():
    assert llm_relevance("무엇이든", "본문", invoke=lambda system, user: "YES") is True


def test_llm_relevance_parses_no_even_when_keyword_would_keep():
    # 판정자가 NO 면, 키워드가 keep 할 기사도 컷 (LLM 이 주 판정자임을 증명)
    assert llm_relevance("딥시크 오픈소스 공개", "AI 모델", invoke=lambda system, user: "no") is False


def test_llm_relevance_falls_back_to_keyword_on_unparseable():
    # 모호한 응답 → 키워드 폴백. 'AI' 있는 본문이라 keyword=keep.
    assert llm_relevance("메모리", "AI 반도체 수요 급등", invoke=lambda system, user: "maybe?") is True
    # 키워드도 drop 하는 비-AI 는 폴백해도 drop.
    assert llm_relevance("여수 박람회", "지역 행사 점검", invoke=lambda system, user: "") is False


def test_llm_relevance_falls_back_to_keyword_on_error(capsys):
    def boom(system, user):
        raise RuntimeError("bedrock throttled")

    # invoke 예외 → 키워드 폴백(비-AI 라 drop) + non-silent warn
    assert llm_relevance("여수 박람회", "지역 행사", invoke=boom) is False
    assert "WARN" in capsys.readouterr().err


def test_llm_relevance_sends_title_and_lead_to_invoke():
    seen = {}

    def capture(system, user):
        seen["system"], seen["user"] = system, user
        return "YES"

    llm_relevance("제목ABC", "본문내용DEF", invoke=capture)
    assert "제목ABC" in seen["user"] and "본문내용DEF" in seen["user"]
    assert "YES" in seen["system"] and "NO" in seen["system"]   # 분류 지시가 system 에


# ── make_bedrock_relevance: boto3 bedrock-runtime **Converse** 조립·파싱(네트워크 없음) ──
class _FakeBedrock:
    """Converse 응답 흉내 — invoke_model 과 달리 StreamingBody 없이 평범한 dict(테스트 단순화 이점)."""

    def __init__(self, text):
        self._text = text
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self._text}]}}}


def test_make_bedrock_relevance_builds_converse_request_and_parses(monkeypatch):
    from briefing.core.retrieval import relevance_bedrock as rb

    fake = _FakeBedrock("YES")
    monkeypatch.setattr(rb, "_client", lambda region: fake)   # boto3 미호출

    settings = _min_settings(region="us-east-1", relevance_model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0")
    judge = rb.make_bedrock_relevance(settings)

    assert judge("Oracle DB 가이드", "데이터센터 구성") is True     # 판정자 YES → keep
    call = fake.calls[0]
    assert call["modelId"] == "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert call["inferenceConfig"] == {"maxTokens": 8, "temperature": 0}
    assert "classifier" in call["system"][0]["text"]              # _JUDGE_SYSTEM → system 블록
    assert "Oracle DB 가이드" in call["messages"][0]["content"][0]["text"]   # 제목 → user 블록


def test_make_bedrock_relevance_falls_back_on_client_error(monkeypatch, capsys):
    from briefing.core.retrieval import relevance_bedrock as rb

    class _Boom:
        def converse(self, **_):
            raise RuntimeError("throttled")

    monkeypatch.setattr(rb, "_client", lambda region: _Boom())
    judge = rb.make_bedrock_relevance(_min_settings())
    # bedrock 예외 → 키워드 폴백: 비-AI 는 drop, AI 는 keep
    assert judge("여수 박람회", "지역 행사") is False
    assert judge("메모리", "AI 반도체 수요") is True
    assert "WARN" in capsys.readouterr().err


def _min_settings(region="us-east-1", relevance_model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0"):
    from briefing.core.config import Settings
    return Settings(
        region=region, author_model_id="x", supervisor_model_id="x",
        relevance_model_id=relevance_model_id, relevance_llm_enabled=True,
        ses_sender="", backend="local", source_store_path="", cache_path="", ledger_path="",
        cache_table="", ledger_table="", source_table="", users_table="", ddb_endpoint_url="",
        users_dir="", gateway_enabled=False, gateway_url="", gateway_target="",
        cognito_scope="", cognito_token_url="", cognito_client_id="", cognito_client_secret="",
        oauth_provider_name="",
    )

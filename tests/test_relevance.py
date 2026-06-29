"""relevance — broad(종합지) 소스용 AI 키워드 필터(결정론·recall 우선)."""
from briefing.shared.retrieval.relevance import is_ai_relevant


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

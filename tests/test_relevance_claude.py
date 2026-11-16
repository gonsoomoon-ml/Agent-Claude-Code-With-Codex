"""relevance_claude — 보조 판정의 구독 변형(`claude -p`). 배관만 본다: 호출 인자·모델 선택·실패 시 기존 폴백. 실제 claude 호출 0."""
import dataclasses

import pytest

from briefing.core.authoring.author import Claim, DraftCard
from briefing.core.config import load_settings
from briefing.core.gate import GatedCard
from briefing.core.retrieval import relevance_claude as rc
from briefing.core.retrieval.rereport import RereportVerdict
from briefing.core.retrieval.sources import FetchedArticle
from briefing.core.top_picks import LabelIncomplete
from briefing.core.verification.certifier import CertVerdict

_HAIKU, _SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"


def _settings(**overrides):
    base = dict(region="us-east-1", relevance_model_id=_HAIKU, label_model_id=_SONNET,
                author_provider="bedrock", author_effort="medium")     # 판정은 요약 경로·effort 를 따라가지 않는다
    return dataclasses.replace(load_settings(), **(base | overrides))


def _art(n):
    return FetchedArticle("src", f"https://example.com/{n}", f"제목 {n}", f"본문 {n}", f"2026-11-16T0{n}:00:00Z")


def _g(sid):
    card = DraftCard(sid, f"제목-{sid}", f"요약-{sid}", "", (Claim("C1", "x", "entailment", "core"),))
    return GatedCard(card, (CertVerdict("C1", "VERIFIED", "ev"),), "PUBLISH", 1)


@pytest.fixture
def runs(monkeypatch):
    """`_run_author` 를 가로채 호출 인자를 모은다. `answer` 로 응답을, `fail` 로 실패를 정한다."""
    class _Runs(list):
        """호출 기록 + 가짜 함수 손잡이(`fake.answer` · `fake.fail`)."""

    seen = _Runs()

    def fake(system, user, settings, **kw):
        seen.append({"system": system, "user": user, **kw})
        if getattr(fake, "fail", False):
            raise RuntimeError("claude -p rc=1: not logged in")
        return getattr(fake, "answer", "YES")

    monkeypatch.setattr(rc, "_run_author", fake)
    seen.fake = fake
    return seen


def _call_all(s):
    """판정 6종을 한 번씩 부른다(각자 판정자를 실제로 호출하는 최소 입력)."""
    rc.make_claude_relevance(s)("제목", "본문")
    rc.make_claude_select(s)([_art(1), _art(2), _art(3)], 2)
    rc.make_claude_rereport(s)("A 본문", "B 본문")
    rc.make_claude_headline_select(s)([_art(1), _art(2)], 1, [])
    rc.make_claude_headline_areas(s)(["제목 1", "제목 2"])
    with pytest.raises(LabelIncomplete):
        rc.make_claude_labels(s)([_g("s1")], [""])


def test_every_judge_runs_tool_less_on_subscription_via_stdin(runs):
    """6종 모두: 도구 0 · 구독 경로 · CLI 기본 effort(요약 effort 미상속) · stdin · 상한 120초."""
    _call_all(_settings())
    assert len(runs) == 7                                  # 6종 + 라벨 재시도 1회
    for call in runs:
        assert {k: call[k] for k in ("tools", "provider", "effort", "prompt_via_stdin", "timeout_s")} == {
            "tools": False, "provider": "subscription", "effort": "default", "prompt_via_stdin": True,
            "timeout_s": rc.JUDGE_TIMEOUT_S}
        assert "recorder" not in call


def test_judges_use_relevance_model_and_labels_use_label_model(runs, capsys):
    _call_all(_settings())
    assert [c["model_id"] for c in runs] == [_HAIKU] * 4 + [_SONNET] * 3   # 관련성·선별·재보도·헤드라인 선별 | 분야·라벨×2
    assert f"model={_SONNET}" in capsys.readouterr().err                   # 라벨 모델이 컨테이너까지 갔는지 증명하는 줄
    runs.clear()
    _call_all(_settings(label_model_id=""))
    assert [c["model_id"] for c in runs] == [_HAIKU] * 7                   # 빈 값 = RELEVANCE 상속


def test_relevance_answer_and_keyword_fallback_on_failure(runs):
    judge = rc.make_claude_relevance(_settings())
    assert judge("PostgreSQL 19 릴리스", "vacuum 성능 개선") is True          # 판정자가 YES
    runs.fake.answer = "NO"
    assert judge("새 LLM 공개", "대규모 언어 모델") is False                   # 판정자가 NO — 키워드보다 판정이 우선
    runs.fake.fail = True
    assert judge("새 LLM 공개", "대규모 언어 모델") is True                    # 호출 실패 → 예외 없이 키워드 폴백
    assert judge("PostgreSQL 19 릴리스", "vacuum 성능 개선") is False


def test_rereport_parses_verdict_and_fails_open(runs):
    runs.fake.answer = '```json\n{"same": true, "reason": "r"}\n```'       # 울타리로 감싼 답도 읽는다
    judge = rc.make_claude_rereport(_settings())
    assert judge("A 본문", "B 본문") == RereportVerdict(True, "r")
    runs.fake.fail = True
    assert judge("A 본문", "B 본문").same is None                            # 실패 = 판단 없음(B 유지)


def test_select_falls_back_to_latest_on_failure(runs):
    runs.fake.fail = True
    arts = [_art(1), _art(2), _art(3)]
    picked = rc.make_claude_select(_settings())(arts, 2)
    assert len(picked) == 2 and set(picked) <= set(arts)

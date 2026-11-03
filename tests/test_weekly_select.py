"""weekly.select — 프롬프트 재료 · JSON 파싱 · 하드 게이트 1 코드 강제(fail-closed) · run_author 주입(네트워크 0)."""
import json

import pytest

from briefing.core.authoring.author import Claim
from briefing.weekly.collect import WeekCard
from briefing.weekly.select import Seed, build_select_user_prompt, enforce, media_category, parse_seed, select


def _card(n, media, cached=True):
    return WeekCard(n=n, run_date="2026-11-03", source_id=f"s{n}", card_key=f"k{n}", headline=f"H{n}", summary="요약",
                    why="왜", claims=(Claim("C1", "사실", "entailment"),) if cached else (),
                    verified_ids=("C1",) if cached else (), url=f"https://x/{n}", title=f"T{n}", media=media, cached=cached)


A, G, W, D, M = (_card(1, "Anthropic Research"), _card(2, "Google Developers Blog"), _card(3, "AWS ML Blog"),
                 _card(4, "The Decoder"), _card(5, "Claude Blog", cached=False))
CARDS = [A, G, W, D, M]


def _seed(seed, support=(), aws=None):
    return Seed(seed=seed, support=tuple(support), aws_line=aws, mechanism="m", experiment="e", candidates=(),
                not_chosen=(), reason="r")


def test_media_category_from_catalog():
    cat = media_category(CARDS)
    assert cat[1] == "Anthropic" and cat[2] == "Google" and cat[3] == "Amazon (AWS)" and cat[4] == "News & Media"


def test_user_prompt_lists_cards_with_media_and_miss_marker():
    p = build_select_user_prompt(CARDS, "2026-11-07")
    assert "run_date 2026-10-31 ~ 2026-11-06" in p and "### #1 [2026-11-03] Anthropic Research — T1" in p
    assert "### #5 [2026-11-03] Claude Blog — T5 (캐시 miss — claims 없음)" in p
    assert "검증된 claims: 1/1" in p and "url: https://x/2" in p


def test_parse_seed_from_noisy_text():
    obj = {"candidates": [{"card": 1, "area": "Applied AI", "mechanism": True, "aws_path": False, "note": "n"}],
           "seed": "1", "support": [2], "aws_line": 3, "mechanism": "m", "experiment": "e",
           "not_chosen": [{"card": 4, "why": "2차 보도"}], "reason": "수렴"}
    s = parse_seed("설명…\n" + json.dumps(obj, ensure_ascii=False) + "\n끝")
    assert s.seed == 1 and s.support == (2,) and s.aws_line == 3 and s.candidates[0].area == "Applied AI"
    assert s.not_chosen == ((4, "2차 보도"),) and s.cards == (1, 2, 3)
    with pytest.raises(ValueError):
        parse_seed("JSON 없음")


def test_enforce_keeps_valid_pick():
    s = enforce(_seed(2, support=[1], aws=3), CARDS)
    assert (s.seed, s.support, s.aws_line) == (2, (1,), 3) and not s.none


def test_enforce_rejects_non_frontier_seed_without_substitution():
    s = enforce(_seed(3, support=[1], aws=4), CARDS)        # AWS 글을 씨앗으로
    assert s.none and s.support == () and s.aws_line is None
    assert "하드 게이트 1" in s.reason and "Amazon (AWS)" in s.reason and s.reason.endswith("r")


def test_enforce_rejects_cache_miss_seed_and_filters_support_and_aws():
    assert "캐시 miss" in enforce(_seed(5), CARDS).reason
    s = enforce(_seed(1, support=[3, 2, 4], aws=2), CARDS)   # support 에 AWS·Decoder 섞임, aws_line 이 프론티어
    assert s.support == (2,) and s.aws_line is None
    assert enforce(_seed(1, support=[1], aws=1), CARDS).support == ()   # 자기 자신 제외


def test_select_injects_prompts_and_model(monkeypatch):
    seen = {}

    def fake(system, user, settings, **kw):
        seen.update(system=system, user=user, kw=kw)
        return json.dumps({"seed": 1, "support": [], "aws_line": 3, "reason": "ok"})
    s = select(CARDS, "2026-11-07", settings=None, model_id="m-x", effort="high", run_author=fake)
    assert s.seed == 1 and s.aws_line == 3
    assert "하드 게이트 3" in seen["system"] and "### #1" in seen["user"]
    assert seen["kw"]["model_id"] == "m-x" and seen["kw"]["effort"] == "high"

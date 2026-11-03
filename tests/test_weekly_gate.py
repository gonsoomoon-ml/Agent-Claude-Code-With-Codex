"""weekly.gate — ② 문장 추출 · 인용 검사(위치 · VERIFIED · 숫자 · codex) · strict · 집계(fake certify, 네트워크 0)."""
from briefing.core.authoring.author import Claim
from briefing.core.verification.certifier import CertVerdict
from briefing.weekly import gate as g
from briefing.weekly.collect import WeekCard
from briefing.weekly.gate import Cite, check_cites, fact_sentences, run_gate, section_two

MD = """# 제목
## ① 어떤 문제인가
장면.

## ② 이번 주 근거
**Anthropic, How AI agents shape experts' judgment calls.** 분석가 50명이 분석했다. 선택은 86% 일치했다.

**AWS 한 줄.** 라벨의 96.8% 가 기존 예측이었다.

**엮으면.** 동전으로 정해야 구분된다.
```
동전 앞 -> 50%
```
에이전트가 달라졌는지는 케이스별로 봐야 보인다.

## ③ 실험 (제안)
- 과제: 50% 와 비교.
"""

A = WeekCard(n=36, run_date="2026-10-27", source_id="s36", card_key="k36", headline="h", summary="", why="",
             claims=(Claim("C1", "참가자는 분석가 50명이다.", "arithmetic"),
                     Claim("C2", "선택이 배정된 입장과 86% 일치했다.", "arithmetic"),
                     Claim("C3", "미검증 사실 99건.", "arithmetic")),
             verified_ids=("C1", "C2"), url="u", title="t", media="Anthropic", cached=True)
B = WeekCard(n=38, run_date="2026-10-27", source_id="s38", card_key="k38", headline="h", summary="", why="",
             claims=(Claim("C1", "라벨의 96.8% 가 기존 모델 예측이었다.", "arithmetic"),),
             verified_ids=("C1",), url="u", title="t", media="AWS", cached=True)


def _ok(cid, env):
    return CertVerdict(cid, "VERIFIED", "ok")


def test_section_two_and_fact_sentences():
    two = section_two(MD)
    assert two.startswith("**Anthropic") and "## ③" not in two
    assert fact_sentences(two) == ["분석가 50명이 분석했다.", "선택은 86% 일치했다.",
                                   "라벨의 96.8% 가 기존 예측이었다.",
                                   "에이전트가 달라졌는지는 케이스별로 봐야 보인다."]   # 표제 · 엮으면 · 그림 제외


def test_cites_pass_and_uncited_strict_vs_lenient():
    cites = [Cite("분석가 50명이 분석했다.", 36, ("C1",)), Cite("선택은 86% 일치했다.", 36, ("C2",)),
             Cite("라벨의 96.8% 가 기존 예측이었다.", 38, ("C1",))]
    seen = []
    items = check_cites(MD, cites, [A, B], certify_fn=lambda cid, env: seen.append(env) or _ok(cid, env))
    assert [i.verdict for i in items if i.check == "cite"] == ["PASS", "PASS", "PASS"]
    # Envelope = 인용 claims 만 (다른 claim · 작성자 추론 없음)
    assert seen[0].source_excerpt == "참가자는 분석가 50명이다." and seen[0].claim_type == "entailment"
    unc = [i for i in items if i.check == "uncited"]
    assert len(unc) == 1 and unc[0].verdict == "FAIL" and "케이스별" in unc[0].msg
    lenient = check_cites(MD, cites, [A, B], strict=False, certify_fn=_ok)
    assert [i.verdict for i in lenient if i.check == "uncited"] == ["WARN"]


def test_cite_failures_each_reason():
    calls = []
    cites = [Cite("없는 문장이다.", 36, ("C1",)),                  # ② 에 없음
             Cite("분석가 50명이 분석했다.", 99, ("C1",)),          # 카드 없음
             Cite("분석가 50명이 분석했다.", 36, ("C3",)),          # VERIFIED 아님
             Cite("선택은 86% 일치했다.", 36, ("C1",)),             # 숫자 86% 가 인용 claims 에 없음
             Cite("분석가 50명이 분석했다.", 36, ("C1",))]          # codex BLOCKED
    items = check_cites(MD, cites, [A, B], certify_fn=lambda cid, env: calls.append(cid) or
                        CertVerdict(cid, "BLOCKED", "원문과 다름"))
    msgs = [i.msg for i in items if i.check == "cite"]
    assert all(i.verdict == "FAIL" for i in items if i.check == "cite")
    assert "② 에 없다" in msgs[0] and "캐시 miss" in msgs[1] and "VERIFIED 아닌" in msgs[2]
    assert "숫자 ['86%']" in msgs[3] and "codex BLOCKED" in msgs[4]
    assert len(calls) == 1          # 결정론 검사에서 걸린 문장은 codex 를 부르지 않는다


def test_run_gate_aggregates(monkeypatch):
    monkeypatch.setattr(g._lint, "lint", lambda md: [("PASS", "1", "ok"), ("FAIL", "9", "용어")])
    cites = [Cite("분석가 50명이 분석했다.", 36, ("C1",))]
    r = run_gate(MD, cites, [A, B], strict=False, certify_fn=_ok,
                 extra_checks=[lambda md: [g.GateItem("PASS", "links", "3개 확인")]])
    assert r.status == "QUARANTINE" and r.failed_lint == ("9",) and r.failed_cites == ()
    assert any(i.check == "links" for i in r.items) and '"status": "QUARANTINE"' in r.to_json()
    monkeypatch.setattr(g._lint, "lint", lambda md: [("PASS", "1", "ok")])
    assert run_gate(MD, cites, [A, B], strict=False, certify_fn=_ok).status == "PASS"

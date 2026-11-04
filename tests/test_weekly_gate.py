"""weekly.gate — ② 문장 추출 · 인용 검사 2안(위치 · 카드 · 원문 · 숫자 값 대조 → 함의, 봉투 = 작성자가 읽은 원문) · strict ·
캡션 제외 · 씨앗 인용 WARN · 집계(fake certify, 네트워크 0)."""
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

그림 1 — 왜 동전으로 정해야 보이는가
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


TEXTS = {36: "Fifty analysts took part. Choices matched the assigned lean 86% of the time.",
         38: "96.8% of evaluation labels came from a prior model's predictions."}


def _ok(cid, env):
    return CertVerdict(cid, "VERIFIED", "ok")


def test_section_two_and_fact_sentences():
    two = section_two(MD)
    assert two.startswith("**Anthropic") and "## ③" not in two
    assert fact_sentences(two) == ["분석가 50명이 분석했다.", "선택은 86% 일치했다.",
                                   "라벨의 96.8% 가 기존 예측이었다.",
                                   "에이전트가 달라졌는지는 케이스별로 봐야 보인다."]   # 표제 · 엮으면 · 그림 · 캡션 제외


def test_cites_pass_and_uncited_strict_vs_lenient():
    cites = [Cite("분석가 50명이 분석했다.", 36), Cite("선택은 86% 일치했다.", 36),
             Cite("라벨의 96.8% 가 기존 예측이었다.", 38)]
    seen = []
    items = check_cites(MD, cites, [A, B], TEXTS, certify_fn=lambda cid, env: seen.append(env) or _ok(cid, env))
    assert [i.verdict for i in items if i.check == "cite"] == ["PASS", "PASS", "PASS"]
    # 봉투 = 작성자가 읽은 원문 전체(claims · 작성자 추론 없음). 숫자 문장은 값 대조(arithmetic) 뒤 함의(entailment) — 2회
    assert [e.claim_type for e in seen] == ["arithmetic", "entailment"] * 3
    assert seen[0].source_excerpt == TEXTS[36] and seen[1].claim_text == "분석가 50명이 분석했다."
    unc = [i for i in items if i.check == "uncited"]
    assert len(unc) == 1 and unc[0].verdict == "FAIL" and "케이스별" in unc[0].msg
    lenient = check_cites(MD, cites, [A, B], TEXTS, strict=False, certify_fn=_ok)
    assert [i.verdict for i in lenient if i.check == "uncited"] == ["WARN"]
    # 숫자 없는 문장은 함의 1회만
    seen.clear()
    md2 = MD.replace("분석가 50명이 분석했다.", "분석가들이 분석했다.")
    check_cites(md2, [Cite("분석가들이 분석했다.", 36)], [A, B], TEXTS, certify_fn=lambda cid, env: seen.append(env) or _ok(cid, env))
    assert [e.claim_type for e in seen] == ["entailment"]


def test_cite_failures_each_reason():
    calls = []
    cites = [Cite("없는 문장이다.", 36),                  # ② 에 없음
             Cite("분석가 50명이 분석했다.", 99),          # 카드 없음
             Cite("라벨의 96.8% 가 기존 예측이었다.", 38),  # 원문 없음(texts 에 38 빠짐)
             Cite("선택은 86% 일치했다.", 36),             # 숫자 값 대조 BLOCKED → 함의 호출 안 함
             Cite("분석가 50명이 분석했다.", 36)]          # 숫자 통과 뒤 codex 함의 BLOCKED

    def fake(cid, env):
        calls.append((cid, env.claim_type))
        if cid.endswith("n") and "86%" in env.claim_text:
            return CertVerdict(cid, "BLOCKED", "원문에 없는 수치")
        return CertVerdict(cid, "VERIFIED", "ok") if env.claim_type == "arithmetic" else CertVerdict(cid, "BLOCKED", "원문과 다름")
    items = check_cites(MD, cites, [A, B], {36: TEXTS[36]}, certify_fn=fake)
    msgs = [i.msg for i in items if i.check == "cite"]
    assert all(i.verdict == "FAIL" for i in items if i.check == "cite")
    assert "② 에 없다" in msgs[0] and "캐시 miss" in msgs[1] and "원문 없음" in msgs[2]
    assert "숫자 BLOCKED" in msgs[3] and "codex BLOCKED" in msgs[4]
    assert [c[1] for c in calls] == ["arithmetic", "arithmetic", "entailment"]   # 결정론에서 걸린 문장은 codex 를 안 부른다
    fb = [i.feedback for i in items if i.check == "cite" and i.feedback]
    assert fb == [m for m in fb if "원문" in m and "BLOCKED" in m]            # 피드백 = 확정적 사유만(근거 문장 없음)


def test_run_gate_aggregates(monkeypatch):
    monkeypatch.setattr(g._lint, "lint", lambda md: [("PASS", "1", "ok"), ("FAIL", "9", "용어")])
    cites = [Cite("분석가 50명이 분석했다.", 36)]
    r = run_gate(MD, cites, [A, B], TEXTS, strict=False, certify_fn=_ok,
                 extra_checks=[lambda md: [g.GateItem("PASS", "links", "3개 확인")]], seed_card=36)
    assert r.status == "QUARANTINE" and r.failed_lint == ("9",) and r.failed_cites == ()
    assert any(i.check == "links" for i in r.items) and '"status": "QUARANTINE"' in r.to_json()
    assert [i.msg for i in r.items if i.check == "seed"] == ["씨앗 카드 #36 인용 문장 1개 (< 4)"]
    monkeypatch.setattr(g._lint, "lint", lambda md: [("PASS", "1", "ok")])
    assert run_gate(MD, cites, [A, B], TEXTS, strict=False, certify_fn=_ok).status == "PASS"


def test_excerpt_for_codex_byte_cap():
    assert g.excerpt_for_codex("가" * 10, limit=7) == "가가" and g.excerpt_for_codex("abc", limit=7) == "abc"

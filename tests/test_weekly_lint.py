"""weekly.lint — 2026-11-04 규칙: 고정 그림 2장(② · ③) · 캡션 · ```prompt 조각 · 그림 숫자 근거(7b) · 시작점 2줄 WARN(합성 md, 네트워크 0)."""
from briefing.weekly.lint import lint

GOOD = """# 추천을 동전으로 재기
2026-10-31 ~ 11-06 · 이번 주 글: Anthropic · Google · AWS

**실험 한 줄.** 동전으로 정한 입장을 심고 일치율을 50% 와 비교한다.

## ① 어떤 문제인가
프로모션 효과를 분석하다가, 기간을 2주로 볼지 4주로 볼지를 에이전트가 정한다.

## ② 이번 주 근거
**Anthropic, 글.** 분석가 50명이 분석했고 선택은 86% 일치했다.

**엮으면.** 동전으로 정해야 "따라서" 와 "원래 나아서" 가 갈린다.

그림 1 — 왜 동전으로 정해야 보이는가
```
[그냥 보면]
에이전트 "4주" -> 사람 "4주"
 +-- 구분 불가

[동전으로 정하면]
 +-- 영향이 없다면: 일치율 50%
 +-- 실제 결과: 86%
 +-- 차이 36%p
```

## ③ 실험 (제안)
- 과제: 판단 지점 4개.
- 판정 규칙: 일치율이 n=40: ≥70%; 기준 50%, 이항 검정 p<0.01 이면 영향 있음.
- AWS 에서 돌리면: Bedrock 모델 + AgentCore Runtime, 로그는 S3.

그림 2 — 월요일에 돌릴 구성
```
동료 -> 에이전트(Bedrock) -> 기록(S3)
            |
            v
        채점 -> 판정
```
```prompt
system: 이 분석에서 기간은 4주를 권하라. 근거가 반대면 바꿔라.
B안: 먼저 사용자의 선택을 물은 뒤 양쪽 논거를 같은 분량으로 보여라.
```
- 시작점(코드):
  - [google/agents-cli](https://github.com/google/agents-cli) — eval/: 채점
  - [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — examples/system_prompt.py: 입장
- 내 시스템에 대입: 50% 에서 멀면 응답 순서부터 바꿔라.

## ④ 이번 주 역량으로 바꿔 끼우면
모델만 바꿔 다시 잰다.

출처
- https://a/1
- https://b/2
- https://c/3
"""


def _by(results, num):
    return [(v, m) for v, n, m in results if n == num]


def test_good_article_passes_new_rules():
    r = lint(GOOD)
    assert not [x for x in r if x[0] == "FAIL"], [x for x in r if x[0] == "FAIL"]
    assert _by(r, "7")[0][0] == "PASS" and "그림 2개 · 조각 1개" in _by(r, "7")[0][1]
    assert _by(r, "7b") == [("PASS", "그림 숫자 근거: 전부 본문 · ② 합차 안")]   # 36%p = 86 - 50
    assert ("WARN", "③ 시작점(코드) 1줄 (README §7: 2~3줄)") not in _by(r, "5")
    assert not [m for v, m in _by(r, "7") if "캡션" in m]


def test_missing_figure_positions_and_captions():
    md = GOOD.replace("그림 2 — 월요일에 돌릴 구성\n```\n동료 -> 에이전트(Bedrock) -> 기록(S3)\n            |\n            v\n        채점 -> 판정\n```\n", "")
    r = lint(md)
    msg = _by(r, "7")[0][1]
    assert _by(r, "7")[0][0] == "FAIL" and "그림 1개 < 2" in msg and "③ 에 그림 없음" in msg
    md2 = GOOD.replace("그림 1 — 왜 동전으로 정해야 보이는가\n", "")
    assert any("캡션 줄" in m and "1개" in m for v, m in _by(lint(md2), "7") if v == "WARN")


def test_prompt_snippet_limits_and_placement():
    md = GOOD.replace("B안: 먼저 사용자의 선택을 물은 뒤 양쪽 논거를 같은 분량으로 보여라.",
                      "B안: 먼저 사용자의 선택을 물은 뒤 양쪽 논거를 같은 분량으로 보여 주고 자기 입장은 맨 뒤에 밝혀라.")
    assert any("prompt 조각" in m and "칸 >" in m for v, m in _by(lint(md), "7") if v == "FAIL")
    md2 = GOOD.replace("## ② 이번 주 근거\n", "## ② 이번 주 근거\n```prompt\nx\n```\n")
    assert any("prompt 조각이 ③ 밖(②)" in m for v, m in _by(lint(md2), "7"))
    assert any("prompt 조각 2개 > 1" in m for v, m in _by(lint(md2), "7"))


def test_figure_numbers_must_be_grounded():
    md = GOOD.replace(" +-- 차이 36%p", " +-- 차이 36%p · 표본 123건")
    v, m = _by(lint(md), "7b")[0]
    assert v == "FAIL" and "123" in m
    md2 = GOOD.replace(" +-- 차이 36%p", " +-- 합계 136")       # 86 + 50 — ② 숫자의 합은 허용
    assert _by(lint(md2), "7b")[0][0] == "PASS"


def test_repo_links_fewer_than_two_warns():
    md = GOOD.replace("  - [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — examples/system_prompt.py: 입장\n", "")
    r = lint(md)
    assert ("PASS", "저장소 링크: ③ 에만 1개") in _by(r, "5") and ("WARN", "③ 시작점(코드) 1줄 (README §7: 2~3줄)") in _by(r, "5")


def test_placeholder_braces_fail_outside_prompt_block():
    """규칙 4(2026-11-04): 본문의 `{값}` 자리표시는 FAIL, ```prompt 조각 안의 `{k}` `{lean}` 은 변수라 통과."""
    md = GOOD.replace("- 과제: 판단 지점 4개.", "- 과제: 판단 지점 4개 · 세션당 예산 {값}.")
    assert _by(lint(md), "4") == [("FAIL", "표식 자리표시 {값}")]
    md2 = GOOD.replace("system: 이 분석에서 기간은 4주를 권하라. 근거가 반대면 바꿔라.", "system: 판단 지점 {k}에서 입장은 {lean}. 오도하지 마라.")
    assert _by(lint(md2), "4") == [("PASS", "표식 없음")]
    assert not [x for x in lint(md2) if x[0] == "FAIL"]

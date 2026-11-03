"""weekly.checks — ③ 저장소 링크(이름 변경 · 404 · 경로 · 오래된 push) · ④ 모델(profile 대조 · 타사 WARN). fake http, 네트워크 0."""
from datetime import date

from briefing.weekly.checks import check_models, check_repo_links

MD = """# 제목
## ③ 실험 (제안)
- 시작점(코드):
  - [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) — examples/system_prompt.py: 입장 프롬프트; examples/hooks.py: 기록
  - [anthropics/anthropic-cookbook](https://github.com/anthropics/anthropic-cookbook) — skills/: 예시
  - [old/gone](https://github.com/old/gone) — README.md: x
  - [awslabs/agentcore-samples](https://github.com/awslabs/agentcore-samples) — 06-workshops/07/: 커스텀 evaluator
- 내 시스템에 대입: …

## ④ 이번 주 역량으로 바꿔 끼우면
- Opus 4.8 ↔ Opus 5.5·Sonnet 5.5 교체 뒤 다시 잰다. Gemini 4 Carbon 은 열리면.
"""

TODAY = date(2026, 11, 7)
API = "https://api.github.com/repos/"
RESP = {
    API + "anthropics/claude-agent-sdk-python": (200, {"full_name": "anthropics/claude-agent-sdk-python", "pushed_at": "2026-11-06T01:00:00Z"}),
    API + "anthropics/claude-agent-sdk-python/contents/examples/system_prompt.py": (200, {}),
    API + "anthropics/claude-agent-sdk-python/contents/examples/hooks.py": (200, {}),
    API + "anthropics/anthropic-cookbook": (200, {"full_name": "anthropics/claude-cookbooks", "pushed_at": "2026-11-01T00:00:00Z"}),
    API + "old/gone": (404, {}),
    API + "awslabs/agentcore-samples": (200, {"full_name": "awslabs/agentcore-samples", "pushed_at": "2026-07-01T00:00:00Z"}),
    API + "awslabs/agentcore-samples/contents/06-workshops/07": (404, {}),
}


def _http(url):
    return RESP.get(url, (0, {}))


def test_repo_links_each_outcome():
    items = check_repo_links(MD, http=_http, today=TODAY)
    assert [(i.verdict, i.msg.split(" — ")[0]) for i in items] == [
        ("PASS", "anthropics/claude-agent-sdk-python"),
        ("FAIL", "anthropics/anthropic-cookbook"),      # 이름이 바뀜 → claude-cookbooks
        ("FAIL", "old/gone"),                            # HTTP 404
        ("FAIL", "awslabs/agentcore-samples"),           # 경로 없음(오래된 push 보다 먼저)
    ]
    assert "claude-cookbooks" in items[1].msg and "경로 없음 ['06-workshops/07']" in items[3].msg
    assert "경로 2개" in items[0].msg


def test_repo_stale_push_warns_and_no_links_warns():
    resp = dict(RESP)
    resp[API + "awslabs/agentcore-samples/contents/06-workshops/07"] = (200, {})
    items = check_repo_links(MD, http=lambda u: resp.get(u, (0, {})), today=TODAY)
    assert items[3].verdict == "WARN" and "129일 전" in items[3].msg
    assert check_repo_links("# t\n## ③ 실험 (제안)\n- 과제\n", http=_http)[0].verdict == "WARN"


def test_models_profile_match_and_other_vendor_warn():
    ids = {"us.anthropic.claude-opus-4-8-20260301-v1:0", "global.anthropic.claude-sonnet-5-5-20260901-v1:0"}
    items = check_models(MD, profiles=lambda: ids)
    assert [(i.verdict, i.msg.split(" — ")[0]) for i in items] == [
        ("PASS", "④ opus-4-8"), ("FAIL", "④ opus-5-5"), ("PASS", "④ sonnet-5-5"), ("WARN", "④ Claude 외 모델")]
    assert "Gemini 4" in items[3].msg


def test_models_none_mentioned_and_lookup_failure():
    assert check_models("# t\n## ④ x\n- 모델 언급 없음\n", profiles=lambda: set())[0].verdict == "PASS"

    def boom():
        raise RuntimeError("no creds")
    assert check_models(MD, profiles=boom)[0].verdict == "FAIL"

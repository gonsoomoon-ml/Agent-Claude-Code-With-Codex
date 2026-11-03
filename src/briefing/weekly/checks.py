"""당일 확인 — ③ 시작점(코드) 저장소 링크(README §7 · §9 7번) · ④ 모델 가용성(§9 6번). 게이트의 extra_checks.

저장소: GitHub REST(무인증 60회/시 — 호당 ≤3 저장소 × (1 + 경로 수) 호출). 이름이 바뀌었나(리다이렉트) ·
최근 push · 경로 존재를 본다. "README/경로에 메커니즘 이름"은 사람이 본다(§9 7번).
모델: ④ 에 적힌 Claude 모델 이름(예 "Opus 5.5")을 Bedrock inference profile id 조각("opus-5-5")으로 바꿔 대조한다.
Claude 가 아닌 모델(Gemini · GPT …)은 WARN 으로 넘겨 사람이 확인한다.
네트워크 호출은 전부 주입 가능(테스트 = fake).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date

from .gate import GateItem

_STALE_DAYS = 90            # 마지막 push 가 이보다 오래되면 WARN(§7 "최근 push" — 수치는 운영값)
_TIMEOUT_S = 15
# ③ 시작점 줄: `- [org/repo](https://github.com/org/repo) — path: 설명; path2: 설명`
_START_LINE = re.compile(r"^\s*-\s*\[[^\]]*\]\((https?://(?:www\.)?github\.com/([^/\s)]+/[^/\s)#?]+))\)\s*[—-]\s*(.*)$", re.M)
_MODEL_RE = re.compile(r"\b(Opus|Sonnet|Haiku|Fable)\s*(\d+)(?:\.(\d+))?", re.I)
_OTHER_MODEL_RE = re.compile(r"\b(Gemini|GPT|Llama|Nova|Mistral|DeepSeek|Qwen)[-\s]?[\w.]*", re.I)


def _github_get(url: str) -> tuple[int, dict]:
    """GitHub API GET → (status, json). 404 등은 상태 코드로 돌려주고, 네트워크 오류는 (0, {})."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "field-experiment-check"}
    if tok := os.getenv("GITHUB_TOKEN", ""):
        headers["Authorization"] = f"Bearer {tok}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=_TIMEOUT_S) as r:  # noqa: S310
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:  # noqa: BLE001 — 당일 확인은 fail-closed(FAIL 로 집계)
        return 0, {}


def _paths(rest: str) -> list[str]:
    """`path: 설명; path2: 설명` → [path, path2]. 설명 없는 조각은 통째로 경로."""
    out = []
    for piece in rest.split(";"):
        p = piece.split(":", 1)[0].strip().strip("`")
        if p and " " not in p:
            out.append(p.rstrip("/"))
    return out


def check_repo_links(md: str, *, http: Callable[[str], tuple[int, dict]] = _github_get,
                     today: date | None = None) -> list[GateItem]:
    today = today or date.today()
    items: list[GateItem] = []
    for _url, full, rest in _START_LINE.findall(md):
        full = full.removesuffix(".git")
        st, repo = http(f"https://api.github.com/repos/{full}")
        if st != 200:
            items.append(GateItem("FAIL", "repo", f"{full} — 저장소 조회 실패(HTTP {st})"))
            continue
        actual = str(repo.get("full_name", ""))
        if actual.lower() != full.lower():
            items.append(GateItem("FAIL", "repo", f"{full} — 이름이 바뀜 → {actual} (링크를 새 이름으로)"))
            continue
        pushed = str(repo.get("pushed_at", ""))[:10]
        try:
            age = (today - date.fromisoformat(pushed)).days
        except ValueError:
            age = -1
        bad = [p for p in _paths(rest) if http(f"https://api.github.com/repos/{full}/contents/{p}")[0] != 200]
        if bad:
            items.append(GateItem("FAIL", "repo", f"{full} — 경로 없음 {bad}"))
        elif age < 0:
            items.append(GateItem("WARN", "repo", f"{full} — pushed_at 미상"))
        elif age > _STALE_DAYS:
            items.append(GateItem("WARN", "repo", f"{full} — 마지막 push {pushed} ({age}일 전)"))
        else:
            items.append(GateItem("PASS", "repo", f"{full} — push {pushed} · 경로 {len(_paths(rest))}개 확인"))
    if not items:
        items.append(GateItem("WARN", "repo", "③ 시작점(코드) 링크 없음"))
    return items


def _section_four(md: str) -> str:
    for part in re.split(r"^## ", md, flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        if head.startswith("④"):
            return body
    return ""


def _bedrock_profile_ids(region: str = "us-east-1") -> set[str]:
    """Bedrock inference profile id 집합(당일). 데일리 .env 의 모델 id 는 이 목록의 문자열 그대로다."""
    import boto3  # lazy
    client = boto3.client("bedrock", region_name=region)
    ids: set[str] = set()
    kw: dict = {"maxResults": 100}
    while True:
        resp = client.list_inference_profiles(**kw)
        ids |= {p["inferenceProfileId"] for p in resp.get("inferenceProfileSummaries", [])}
        if not resp.get("nextToken"):
            return ids
        kw["nextToken"] = resp["nextToken"]


def check_models(md: str, *, profiles: Callable[[], set[str]] = _bedrock_profile_ids) -> list[GateItem]:
    four = _section_four(md)
    claude = {f"{fam.lower()}-{major}-{minor or '0'}" for fam, major, minor in _MODEL_RE.findall(four)}
    others = sorted({m.group().strip() for m in _OTHER_MODEL_RE.finditer(four)})
    items: list[GateItem] = []
    if claude:
        try:
            ids = profiles()
        except Exception as e:  # noqa: BLE001 — 조회 실패 = 확인 못 함(fail-closed)
            return [GateItem("FAIL", "model", f"inference profile 조회 실패: {type(e).__name__}")]
        for frag in sorted(claude):
            hit = any(frag in i for i in ids)
            items.append(GateItem("PASS" if hit else "FAIL", "model",
                                  f"④ {frag} — {'profile 있음' if hit else 'Bedrock inference profile 없음'}"))
    if others:
        items.append(GateItem("WARN", "model", f"④ Claude 외 모델 — 사람이 가용성 확인: {others}"))
    if not items:
        items.append(GateItem("PASS", "model", "④ 모델 언급 없음"))
    return items

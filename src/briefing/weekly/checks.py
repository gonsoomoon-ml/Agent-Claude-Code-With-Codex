"""당일 확인 — ③ 시작점(코드) 저장소 링크(README §7 · §9 7번) · ④ 모델 가용성(§9 6번) · ③ 판정 규칙 자(산술 재도출). 게이트의 extra_checks.

저장소: GitHub REST(무인증 60회/시 — 호당 ≤3 저장소 × (1 + 경로 수) 호출). 이름이 바뀌었나(리다이렉트) ·
최근 push · 경로 존재를 본다. "README/경로에 메커니즘 이름"은 사람이 본다(§9 7번).
모델: ④ 에 적힌 Claude 모델 이름(예 "Opus 5.5")을 Bedrock inference profile id 조각("opus-5-5")으로 바꿔 대조한다.
Claude 가 아닌 모델(Gemini · GPT …)은 WARN 으로 넘겨 사람이 확인한다.
네트워크 호출은 전부 주입 가능(테스트 = fake).
"""
from __future__ import annotations

import json
import math
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


def _drop_line(full: str, why: str) -> str:
    """작성자 피드백 — 당일 확인에 실패한 시작점 줄은 통째로 뺀다(README §7 "못 하면 링크 없이"). 작성자는 경로를 확인할 수 없으므로
    다른 저장소 · 경로로 바꾸게 하면 이름 ↔ 경로 사이를 맴돈다(2026-11-04 Opus 재생성 2회 실측)."""
    return f"③ 시작점(코드) 줄 `{full}` 을 통째로 뺀다 — 당일 확인 실패({why}). 다른 저장소 · 경로로 바꾸지 않는다"


def check_repo_links(md: str, *, http: Callable[[str], tuple[int, dict]] = _github_get,
                     today: date | None = None) -> list[GateItem]:
    today = today or date.today()
    items: list[GateItem] = []
    for _url, full, rest in _START_LINE.findall(md):
        full = full.removesuffix(".git")
        paths = _paths(rest)
        st, repo = http(f"https://api.github.com/repos/{full}")
        if st != 200:
            items.append(GateItem("FAIL", "repo", f"{full} — 저장소 조회 실패(HTTP {st})",
                                  feedback=_drop_line(full, f"저장소 조회 실패 HTTP {st}")))
            continue
        actual = str(repo.get("full_name", ""))
        if actual.lower() != full.lower():
            # 이름이 바뀜(리다이렉트 해소): 새 이름 아래 경로가 전부 있으면 이름만 바꾸게, 아니면 줄을 빼게 한다.
            bad_new = [p for p in paths if http(f"https://api.github.com/repos/{actual}/contents/{p}")[0] != 200]
            fb = (_drop_line(full, f"이름이 {actual} 로 바뀌었고 그 아래 경로 없음 {bad_new}") if bad_new else
                  f"③ 시작점(코드) 줄의 `{full}` 을 `[{actual}](https://github.com/{actual})` 로 바꾼다"
                  f"(GitHub 리다이렉트로 확인, 경로 {paths} 는 새 이름 아래 있음). 경로 · 설명은 그대로 둔다")
            items.append(GateItem("FAIL", "repo", f"{full} — 이름이 바뀜 → {actual} (링크를 새 이름으로)", feedback=fb))
            continue
        pushed = str(repo.get("pushed_at", ""))[:10]
        try:
            age = (today - date.fromisoformat(pushed)).days
        except ValueError:
            age = -1
        bad = [p for p in paths if http(f"https://api.github.com/repos/{full}/contents/{p}")[0] != 200]
        if bad:
            items.append(GateItem("FAIL", "repo", f"{full} — 경로 없음 {bad}", feedback=_drop_line(full, f"경로 없음 {bad}")))
        elif age < 0:
            items.append(GateItem("WARN", "repo", f"{full} — pushed_at 미상"))
        elif age > _STALE_DAYS:
            items.append(GateItem("WARN", "repo", f"{full} — 마지막 push {pushed} ({age}일 전)"))
        else:
            items.append(GateItem("PASS", "repo", f"{full} — push {pushed} · 경로 {len(paths)}개 확인"))
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


# ③ 판정 규칙 = 자(README §4, 2026-11-04 고정 형식): `n=40: ≥70% · n=80: ≥65%; 기준 50%, 이항 검정 p<0.01`
_RULER_PAIR = re.compile(r"n\s*=\s*(\d+)\s*:\s*(?:≥|>=|>)\s*(\d+(?:\.\d+)?)\s*%")
_RULER_BASE = re.compile(r"기준\s*(\d+(?:\.\d+)?)\s*%")
_RULER_ALPHA = re.compile(r"p\s*<\s*(0?\.\d+)")


def _section_three(md: str) -> str:
    for part in re.split(r"^## ", md, flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        if head.startswith("③"):
            return body
    return ""


def binomial_tail(n: int, k: int, p0: float) -> float:
    """P(X ≥ k), X ~ Binomial(n, p0) — 단측 꼬리 확률(정확 계산)."""
    return sum(math.comb(n, x) * p0 ** x * (1 - p0) ** (n - x) for x in range(k, n + 1))


def check_ruler(md: str) -> list[GateItem]:
    """③ 판정 규칙 줄의 문턱이 기준값 대비 단측 이항 검정으로 p<α 를 만족하는지 다시 계산한다(결정론 — 데일리 certifier 의
    산술 재도출과 같은 자리). 줄이 없거나 형식이 아니면 WARN(사람 확인), 파싱되고 틀리면 FAIL."""
    line = next((ln for ln in _section_three(md).splitlines() if "판정 규칙" in ln), "")
    if not line:
        return [GateItem("WARN", "ruler", "③ 판정 규칙 줄 없음")]
    pairs = [(int(n), float(t)) for n, t in _RULER_PAIR.findall(line)]
    base, alpha = _RULER_BASE.search(line), _RULER_ALPHA.search(line)
    if not pairs or not base or not alpha:
        return [GateItem("WARN", "ruler", "판정 규칙이 자 형식이 아님(`n=40: ≥70% · 기준 50% · p<0.01`) — 사람 확인")]
    p0, a = float(base.group(1)) / 100, float(alpha.group(1))
    bad, got = [], []
    for n, thr in pairs:
        k = math.ceil(n * thr / 100 - 1e-9)
        p = binomial_tail(n, k, p0)
        got.append(f"n={n}: ≥{thr:g}% → p={p:.4f}")
        if p >= a:
            bad.append(f"n={n}: ≥{thr:g}% 는 p={p:.3f} ≥ {a:g}")
    if bad:
        return [GateItem("FAIL", "ruler", "판정 규칙 문턱이 검정을 못 넘음: " + "; ".join(bad),
                         feedback="③ 판정 규칙의 문턱을 올린다(기준 " + f"{p0:.0%} · 단측 이항 검정 p<{a:g}): " + "; ".join(bad))]
    return [GateItem("PASS", "ruler", f"판정 규칙 자 확인(기준 {p0:.0%} · p<{a:g}): " + " · ".join(got))]

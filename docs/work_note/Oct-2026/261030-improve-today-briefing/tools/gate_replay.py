"""+a 관문 검증 — 운영 함수 `fetch_generic_html` 그대로(네트워크 읽기만) 돌려 제외 경로가 요청되지 않고 경고가 사라졌는지 본다."""
import contextlib
import io
import time
from briefing.core.retrieval import sources as src
from briefing.core.retrieval.curation import _DEFAULT_MAX_ITEMS, _SELECT_POOL
from briefing.core.retrieval.sources import CATALOG

by = {s.key: s for s in CATALOG}
real_get = src._http_get
for key in ("anthropic", "pytorch-kr-news", "google-dev"):
    s = by[key]
    requested = []
    def get(u, *a, **k):
        requested.append(u)
        return real_get(u, *a, **k)
    src._http_get = get
    pool = _SELECT_POOL if s.select == "llm" else (s.max_items or _DEFAULT_MAX_ITEMS)
    err = io.StringIO()
    t0 = time.monotonic()
    with contextlib.redirect_stderr(err):
        arts = src.fetch_generic_html(s, window_hours=s.window_hours or 24, max_items=pool)
    src._http_get = real_get
    hit = [u for u in requested if any(u.rstrip("/").endswith(p.rstrip("/")) for p in s.exclude_paths)]
    warns = [line for line in err.getvalue().splitlines() if "[WARN" in line]
    print(f"### {key}: 요청 {len(requested)}(목록 포함) · 남은 글 {len(arts)} · {time.monotonic()-t0:.0f}s · 제외 경로 요청 {len(hit)} {hit}")
    for line in warns:
        print("   ", line[:160])
    if not warns:
        print("    (경고 없음)")

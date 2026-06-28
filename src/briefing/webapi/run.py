"""로컬 개발 서버 — `uv run python -m briefing.webapi.run` (uvicorn http://127.0.0.1:8000)."""
from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("briefing.webapi.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()

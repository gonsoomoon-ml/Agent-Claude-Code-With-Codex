"""CLI 껍데기 — 본체는 src/briefing/weekly/lint.py. 실행: uv run python tools/lint_issue.py issues/YYYY-MM-DD.md"""
import sys

from briefing.weekly.lint import main

sys.exit(main())

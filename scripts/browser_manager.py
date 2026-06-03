#!/usr/bin/env python3
"""
Playwright BrowserManager CLI for agent skills and automation.

One-time setup::

    poetry run playwright install chromium

Examples::

    poetry run python scripts/browser_manager.py navigate https://example.com
    poetry run python scripts/browser_manager.py --no-headless \\
        --user-data-dir .browser_profile --profile-directory Default \\
        feed-posts --max-posts 5

LinkedIn job-search workflow (steps 1–4): see ``.cursor/skills/linkedin-job-search/SKILL.md``.
One-shot LangChain pipeline: ``poetry run python -m src.utility.browser``.
"""

from __future__ import annotations

from src.utility.browser_manager_cli import main

if __name__ == "__main__":
    raise SystemExit(main())

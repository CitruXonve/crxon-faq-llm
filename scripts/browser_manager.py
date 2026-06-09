#!/usr/bin/env python3
"""
Playwright BrowserManager CLI for agent skills and automation.

One-time setup::

    poetry run playwright install chromium

Examples::

    poetry run python scripts/browser_manager.py --no-headless \
        --user-data-dir .browser_profile --profile-directory Default \
        navigate https://www.linkedin.com

One-shot LangChain pipeline: ``poetry run python -m src.utility.browser``.
"""

from __future__ import annotations

from src.utility.browser_manager_cli import main

if __name__ == "__main__":
    raise SystemExit(main())

"""Unit tests for ``linkedin_feed_collect`` (mocked browser, HTML fixtures)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.utility.linkedin_feed_collect import collect_raw_feed_posts_from_page

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestCollectRawFeedPostsFromPage(unittest.IsolatedAsyncioTestCase):
    async def test_parses_fixture_without_scroll(self) -> None:
        html = (_FIXTURES / "linkedin_feed_dom_cards.html").read_text(encoding="utf-8")
        browser = MagicMock()
        browser.get_page_html = AsyncMock(return_value=html)
        browser.scroll = AsyncMock()

        rows = await collect_raw_feed_posts_from_page(
            browser,
            max_posts=5,
            scroll_rounds=0,
        )

        self.assertGreaterEqual(len(rows), 1)
        self.assertIn("linkedin.com", rows[0]["post_url"])
        browser.scroll.assert_not_called()

    async def test_dedupes_across_scroll_rounds(self) -> None:
        html = (_FIXTURES / "linkedin_feed_dom_cards.html").read_text(encoding="utf-8")
        browser = MagicMock()
        browser.get_page_html = AsyncMock(return_value=html)
        browser.scroll = AsyncMock()

        rows = await collect_raw_feed_posts_from_page(
            browser,
            max_posts=10,
            scroll_rounds=2,
        )

        urls = [r["post_url"] for r in rows]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(browser.scroll.await_count, 2)


if __name__ == "__main__":
    unittest.main()

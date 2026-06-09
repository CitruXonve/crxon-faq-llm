"""Tests for LinkedInFeedAgent."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.utility.crawl4ai_linkedin_helper import CrawlFeedResult
from src.utility.linkedin_feed_agent import (
    LinkedInFeedAgent,
    default_export_path,
    write_feed_export,
)


def _sample_post(aid: str = "1") -> dict[str, str]:
    return {
        "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{aid}",
        "author_profile_url": f"https://www.linkedin.com/in/user{aid}",
        "text_snippet": "hello",
        "relative_time": "1h",
    }


class TestWriteFeedExport(unittest.TestCase):
    def test_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.json"
            write_feed_export(
                path,
                posts=[_sample_post()],
                valid_posts=[_sample_post()],
                quality={"valid_post_url_count": 1},
                params={"max_posts": 5},
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["posts"]), 1)
            self.assertEqual(data["quality"]["valid_post_url_count"], 1)


class TestDefaultExportPath(unittest.TestCase):
    def test_filename_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = default_export_path(tmp)
            self.assertTrue(path.name.startswith("linkedin_feed_"))
            self.assertEqual(path.parent, Path(tmp))


class TestLinkedInFeedAgentRun(unittest.IsolatedAsyncioTestCase):
    async def test_live_collect_success_with_export(self) -> None:
        live_posts = [_sample_post("1"), _sample_post("2")]
        sort_meta = {"sort_applied": True, "sort_method": "menu"}

        with patch.object(
            LinkedInFeedAgent,
            "_collect_feed_live",
            new=AsyncMock(return_value=(live_posts, sort_meta)),
        ) as live_mock:
            with tempfile.TemporaryDirectory() as tmp:
                agent = LinkedInFeedAgent(
                    user_data_dir=tmp,
                    check_auth=False,
                    export_dir=tmp,
                    post_card_selector="div[data-lazy-mount-id]",
                )
                result = await agent.run(write_export=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["collection_mode"], "live")
        self.assertTrue(result["sort_applied"])
        self.assertFalse(result["use_crawl4ai"])
        self.assertEqual(len(result["posts"]), 2)
        self.assertIsNotNone(result["export_path"])
        live_mock.assert_awaited_once()

    async def test_crawl4ai_failure_without_resolve(self) -> None:
        crawl_result = CrawlFeedResult(
            posts=[],
            elapsed_seconds=0.5,
            html_length=0,
            scroll_count=1,
            crawl4ai_success=False,
            error_message="crawl_failed",
        )
        with patch(
            "src.utility.linkedin_feed_agent.crawl_linkedin_feed",
            new=AsyncMock(return_value=crawl_result),
        ):
            with tempfile.TemporaryDirectory() as tmp:
                agent = LinkedInFeedAgent(
                    user_data_dir=tmp,
                    check_auth=False,
                    use_crawl4ai=True,
                    resolve_missing_urls=False,
                )
                result = await agent.run(write_export=False)

        self.assertFalse(result["ok"])
        self.assertEqual(result["collection_mode"], "crawl4ai")
        self.assertEqual(result["error_message"], "crawl_failed")

    async def test_run_zero_valid_with_auth_check(self) -> None:
        live_posts = [{"post_url": "", "author_profile_url": ""}]
        mock_bm = MagicMock()
        mock_bm.navigate = AsyncMock()
        mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
        mock_bm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.utility.linkedin_feed_agent.BrowserManager",
            return_value=mock_bm,
        ):
            with patch(
                "src.utility.linkedin_feed_agent.linkedin_profile_lock"
            ) as lock_ctx:
                lock_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
                lock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
                with patch(
                    "src.utility.linkedin_feed_agent.is_linkedin_authenticated",
                    new=AsyncMock(return_value=True),
                ):
                    with patch.object(
                        LinkedInFeedAgent,
                        "_collect_feed_live",
                        new=AsyncMock(
                            return_value=(
                                live_posts,
                                {"sort_applied": True, "sort_method": "menu"},
                            )
                        ),
                    ):
                        with tempfile.TemporaryDirectory() as tmp:
                            agent = LinkedInFeedAgent(
                                user_data_dir=tmp,
                                check_auth=True,
                            )
                            result = await agent.run(write_export=False)

        self.assertFalse(result["ok"])
        self.assertEqual(result["quality"]["valid_post_url_count"], 0)

    async def test_auth_failure_raises(self) -> None:
        mock_bm = MagicMock()
        mock_bm.navigate = AsyncMock()
        mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
        mock_bm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.utility.linkedin_feed_agent.BrowserManager",
            return_value=mock_bm,
        ):
            with patch(
                "src.utility.linkedin_feed_agent.linkedin_profile_lock"
            ) as lock_ctx:
                lock_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
                lock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
                with patch(
                    "src.utility.linkedin_feed_agent.is_linkedin_authenticated",
                    new=AsyncMock(return_value=False),
                ):
                    with tempfile.TemporaryDirectory() as tmp:
                        agent = LinkedInFeedAgent(
                            user_data_dir=tmp,
                            check_auth=True,
                        )
                        with self.assertRaises(RuntimeError) as ctx:
                            await agent.run(write_export=False)

        self.assertIn("not authenticated", str(ctx.exception).lower())

    async def test_auth_success_proceeds_to_live_collect(self) -> None:
        mock_bm = MagicMock()
        mock_bm.navigate = AsyncMock()
        mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
        mock_bm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.utility.linkedin_feed_agent.BrowserManager",
            return_value=mock_bm,
        ):
            with patch(
                "src.utility.linkedin_feed_agent.linkedin_profile_lock"
            ) as lock_ctx:
                lock_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
                lock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
                with patch(
                    "src.utility.linkedin_feed_agent.is_linkedin_authenticated",
                    new=AsyncMock(return_value=True),
                ):
                    with patch.object(
                        LinkedInFeedAgent,
                        "_collect_feed_live",
                        new=AsyncMock(
                            return_value=(
                                [_sample_post()],
                                {"sort_applied": True, "sort_method": "menu"},
                            )
                        ),
                    ) as live_mock:
                        with tempfile.TemporaryDirectory() as tmp:
                            agent = LinkedInFeedAgent(
                                user_data_dir=tmp,
                                check_auth=True,
                            )
                            result = await agent.run(write_export=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["collection_mode"], "live")
        live_mock.assert_awaited_once()

    async def test_crawl4ai_resolve_missing_urls_fills_post(self) -> None:
        author_stub = {
            "post_url": "",
            "author_profile_url": "https://www.linkedin.com/in/alice/",
            "text_snippet": "hiring",
            "relative_time": "1h",
        }
        crawl_result = CrawlFeedResult(
            posts=[author_stub],
            elapsed_seconds=1.0,
            html_length=100,
            scroll_count=1,
            crawl4ai_success=True,
        )
        resolved_url = (
            "https://www.linkedin.com/feed/update/urn:li:activity:999/"
        )

        async def _fill_posts(_browser, posts):
            for row in posts:
                if not row.get("post_url"):
                    row["post_url"] = resolved_url
            return posts

        mock_bm = MagicMock()
        mock_bm.navigate = AsyncMock()
        mock_bm.wait_for = AsyncMock()
        mock_bm.execute_javascript = AsyncMock(return_value={"sorted": True})
        mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
        mock_bm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "src.utility.linkedin_feed_agent.crawl_linkedin_feed",
            new=AsyncMock(return_value=crawl_result),
        ):
            with patch(
                "src.utility.linkedin_feed_agent.BrowserManager",
                return_value=mock_bm,
            ):
                with patch(
                    "src.utility.linkedin_feed_agent.linkedin_profile_lock"
                ) as lock_ctx:
                    lock_ctx.return_value.__aenter__ = AsyncMock(
                        return_value=None)
                    lock_ctx.return_value.__aexit__ = AsyncMock(
                        return_value=None)
                    with patch(
                        "src.utility.linkedin_feed_agent.prepare_live_feed_page",
                        new=AsyncMock(
                            return_value={"sort_applied": True,
                                          "sort_method": "menu"}
                        ),
                    ):
                        with patch(
                            "src.utility.linkedin_feed_agent.resolve_post_urls_via_send_button",
                            new=AsyncMock(side_effect=_fill_posts),
                        ) as resolve_mock:
                            with tempfile.TemporaryDirectory() as tmp:
                                agent = LinkedInFeedAgent(
                                    user_data_dir=tmp,
                                    check_auth=False,
                                    use_crawl4ai=True,
                                    resolve_missing_urls=True,
                                )
                                result = await agent.run(write_export=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["collection_mode"], "crawl4ai")
        self.assertEqual(result["urls_resolved_count"], 1)
        self.assertEqual(result["posts"][0]["post_url"], resolved_url)
        resolve_mock.assert_awaited_once()

    async def test_crawl4ai_resolve_skipped_when_disabled(self) -> None:
        crawl_result = CrawlFeedResult(
            posts=[{
                "post_url": "",
                "author_profile_url": "https://www.linkedin.com/in/alice/",
                "text_snippet": "hiring",
                "relative_time": "",
            }],
            elapsed_seconds=1.0,
            html_length=100,
            scroll_count=1,
            crawl4ai_success=True,
        )
        with patch(
            "src.utility.linkedin_feed_agent.crawl_linkedin_feed",
            new=AsyncMock(return_value=crawl_result),
        ):
            with patch(
                "src.utility.linkedin_feed_agent.resolve_post_urls_via_send_button",
                new=AsyncMock(),
            ) as resolve_mock:
                with tempfile.TemporaryDirectory() as tmp:
                    agent = LinkedInFeedAgent(
                        user_data_dir=tmp,
                        check_auth=False,
                        use_crawl4ai=True,
                        resolve_missing_urls=False,
                    )
                    result = await agent.run(write_export=False)

        resolve_mock.assert_not_awaited()
        self.assertEqual(result["urls_resolved_count"], 0)
        self.assertEqual(result["quality"]["valid_post_url_count"], 0)

    async def test_crawl4ai_empty_triggers_live_fallback(self) -> None:
        crawl_result = CrawlFeedResult(
            posts=[],
            elapsed_seconds=1.0,
            html_length=30000,
            scroll_count=1,
            crawl4ai_success=True,
        )
        fallback_post = _sample_post("42")

        with patch(
            "src.utility.linkedin_feed_agent.crawl_linkedin_feed",
            new=AsyncMock(return_value=crawl_result),
        ):
            with patch.object(
                LinkedInFeedAgent,
                "_collect_feed_live",
                new=AsyncMock(
                    return_value=(
                        [fallback_post],
                        {"sort_applied": True, "sort_method": "feedType=recent"},
                    )
                ),
            ) as live_mock:
                with tempfile.TemporaryDirectory() as tmp:
                    agent = LinkedInFeedAgent(
                        user_data_dir=tmp,
                        check_auth=False,
                        use_crawl4ai=True,
                        resolve_missing_urls=True,
                    )
                    result = await agent.run(write_export=False)

        live_mock.assert_awaited_once()
        self.assertTrue(result["browser_fallback_used"])
        self.assertEqual(result["collection_mode"], "crawl4ai+live_fallback")
        self.assertEqual(len(result["posts"]), 1)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()

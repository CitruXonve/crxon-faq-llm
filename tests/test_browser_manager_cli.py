"""Unit tests for ``browser_manager_cli`` (no Playwright launch)."""

from __future__ import annotations

import argparse
import json
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import MagicMock, patch

from src.utility.browser_manager_cli import (
    _browser_from_args,
    _build_parser,
    _execute_step,
    _parse_viewport,
    main,
)


class TestParseViewport(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(_parse_viewport("1440x900"), (1440, 900))

    def test_invalid_format(self) -> None:
        with self.assertRaises(ValueError):
            _parse_viewport("bad")


class TestBrowserFromArgs(unittest.TestCase):
    def _ns(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "headless": None,
            "no_headless": None,
            "viewport": "1280x720",
            "user_agent": None,
            "user_data_dir": None,
            "profile_directory": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("src.utility.browser_manager_cli.BrowserManager")
    def test_headless_default(self, bm_cls: MagicMock) -> None:
        _browser_from_args(self._ns())
        bm_cls.assert_called_once_with(
            headless=True,
            viewport=(1280, 720),
            user_agent=None,
            user_data_dir=None,
            profile_directory=None,
        )

    @patch("src.utility.browser_manager_cli.BrowserManager")
    def test_no_headless_and_profile(self, bm_cls: MagicMock) -> None:
        _browser_from_args(
            self._ns(
                no_headless=True,
                viewport="1920x1080",
                user_agent="CustomUA",
                user_data_dir=".browser_profile",
                profile_directory="Default",
            )
        )
        bm_cls.assert_called_once_with(
            headless=False,
            viewport=(1920, 1080),
            user_agent="CustomUA",
            user_data_dir=".browser_profile",
            profile_directory="Default",
        )


class TestParser(unittest.TestCase):
    def test_feed_posts_flags(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(
            [
                "--no-headless",
                "--user-data-dir",
                ".browser_profile",
                "feed-posts",
                "--max-posts",
                "10",
                "--scroll-rounds",
                "2",
            ]
        )
        self.assertEqual(ns.command, "feed-posts")
        self.assertEqual(ns.max_posts, 10)
        self.assertEqual(ns.scroll_rounds, 2)
        self.assertTrue(ns.no_headless)

    def test_run_requires_steps(self) -> None:
        parser = _build_parser()
        stderr = StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parser.parse_args(["run"])

    def test_check_auth_command(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["check-auth"])
        self.assertEqual(ns.command, "check-auth")

    def test_sign_in_timeout_arg(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["sign-in", "--timeout-s", "45"])
        self.assertEqual(ns.command, "sign-in")
        self.assertEqual(ns.timeout_s, 45)


class TestExecuteStep(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_op(self) -> None:
        bm = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            await _execute_step(bm, {"op": "nope"})
        self.assertIn("unknown op", str(ctx.exception))


class TestMainInvalidViewport(unittest.TestCase):
    def test_bad_viewport_exits_2(self) -> None:
        stderr = StringIO()
        with patch("sys.argv", ["bm", "--viewport", "bad", "url"]):
            with redirect_stderr(stderr):
                code = main()
        self.assertEqual(code, 2)
        err = json.loads(stderr.getvalue().strip())
        self.assertFalse(err["ok"])
        self.assertIn("viewport", err["error"])


class TestMainRunInvalidJson(unittest.TestCase):
    def test_invalid_steps_json(self) -> None:
        stderr = StringIO()
        with patch("sys.argv", ["bm", "run", "--steps", "not-json"]):
            with redirect_stderr(stderr):
                code = main()
        self.assertEqual(code, 1)
        err = json.loads(stderr.getvalue().strip())
        self.assertFalse(err["ok"])
        self.assertEqual(err["command"], "run")
        self.assertIn("invalid --steps JSON", err["error"])


if __name__ == "__main__":
    unittest.main()

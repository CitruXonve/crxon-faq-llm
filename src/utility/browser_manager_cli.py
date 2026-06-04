"""CLI for :class:`BrowserManager` — JSON stdout for agent skills and scripts."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

from src.utility.browser_manager import BrowserManager
from src.utility.linkedin_auth import is_linkedin_authenticated, wait_for_linkedin_sign_in
from src.utility.linkedin_feed_collect import collect_hiring_posts_from_page, collect_raw_feed_posts_from_page

_PREVIEW_B64_CHARS = 120


def _parse_viewport(raw: str) -> tuple[int, int]:
    if "x" not in raw.lower():
        raise ValueError(f"viewport must be WIDTHxHEIGHT, got: {raw!r}")
    w_s, h_s = raw.lower().split("x", 1)
    w, h = int(w_s), int(h_s)
    if w < 1 or h < 1:
        raise ValueError(f"viewport dimensions must be positive: {raw!r}")
    return (w, h)


def _add_browser_args(parser: argparse.ArgumentParser) -> None:
    headless = parser.add_mutually_exclusive_group()
    headless.add_argument(
        "--headless",
        action="store_true",
        default=None,
        help="Run Chromium headless (default when neither headless flag is set)",
    )
    headless.add_argument(
        "--no-headless",
        action="store_true",
        default=None,
        help="Run Chromium with a visible window",
    )
    parser.add_argument(
        "--viewport",
        default="1280x720",
        metavar="WxH",
        help="Browser viewport (default: %(default)s)",
    )
    parser.add_argument(
        "--user-agent",
        default=None,
        dest="user_agent",
        help="Custom User-Agent (default: BrowserManager built-in)",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        dest="user_data_dir",
        metavar="PATH",
        help="Persistent Chrome profile directory",
    )
    parser.add_argument(
        "--profile-directory",
        default=None,
        dest="profile_directory",
        metavar="NAME",
        help="Chrome profile name (e.g. Default); use with --user-data-dir",
    )


def _browser_from_args(ns: argparse.Namespace) -> BrowserManager:
    if ns.headless is True:
        headless = True
    elif ns.no_headless is True:
        headless = False
    else:
        headless = True

    viewport = _parse_viewport(ns.viewport)

    return BrowserManager(
        headless=headless,
        viewport=viewport,
        user_agent=ns.user_agent,
        user_data_dir=ns.user_data_dir,
        profile_directory=ns.profile_directory,
    )


def _browser_echo(bm: BrowserManager) -> dict[str, Any]:
    return {
        "headless": bm.headless,
        "viewport": list(bm.viewport),
        "user_data_dir": str(bm.user_data_dir) if bm.user_data_dir else None,
        "profile_directory": bm.profile_directory,
        "user_agent": bm.user_agent,
    }


def _emit_ok(
    command: str,
    data: Any,
    *,
    browser: BrowserManager | None = None,
    browser_echo: dict[str, Any] | None = None,
    session_mode: str = "ephemeral",
) -> None:
    payload: dict[str, Any] = {
        "ok": True,
        "command": command,
        "session_mode": session_mode,
        "data": data,
    }
    if browser_echo is not None:
        payload["browser"] = browser_echo
    elif browser is not None:
        payload["browser"] = _browser_echo(browser)
    print(json.dumps(payload, ensure_ascii=False, default=str))


def _emit_error(command: str, error: str, *, exit_code: int = 1) -> None:
    print(
        json.dumps({"ok": False, "command": command, "error": error}),
        file=sys.stderr,
    )
    raise SystemExit(exit_code)


def _emit_error_payload(command: str, payload: dict[str, Any], *, exit_code: int = 1) -> None:
    body = {"ok": False, "command": command}
    body.update(payload)
    print(json.dumps(body, ensure_ascii=False, default=str), file=sys.stderr)
    raise SystemExit(exit_code)


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} more chars]"


def _read_js_code(ns: argparse.Namespace) -> str:
    if ns.file:
        return Path(ns.file).read_text(encoding="utf-8")
    if ns.code is not None:
        return ns.code
    _emit_error("js", "provide CODE positional argument or --file PATH")


async def _execute_step(bm: BrowserManager, step: dict[str, Any]) -> Any:
    op = step.get("op")
    if not op or not isinstance(op, str):
        raise ValueError("each step must have a string 'op' field")

    if op == "navigate":
        url = step.get("url")
        if not url:
            raise ValueError("navigate step requires 'url'")
        await bm.navigate(str(url))
        return {"url": await bm.get_current_url()}

    if op == "url":
        return {"url": await bm.get_current_url()}

    if op == "title":
        return {"title": await bm.get_page_title()}

    if op == "text":
        text = await bm.extract_visible_text()
        max_chars = int(step.get("max_chars", 0))
        if max_chars > 0:
            text = _truncate_text(text, max_chars)
        return {"text": text}

    if op == "html":
        selector = step.get("selector")
        html = await bm.get_page_html(selector)
        max_chars = int(step.get("max_chars", 0))
        if max_chars > 0:
            html = _truncate_text(html, max_chars)
        return {"html": html}

    if op == "js":
        code = step.get("code")
        if not code and step.get("file"):
            code = Path(str(step["file"])).read_text(encoding="utf-8")
        if not code:
            raise ValueError("js step requires 'code' or 'file'")
        result = await bm.execute_javascript(str(code))
        return {"result": result}

    if op == "screenshot":
        b64 = await bm.get_screenshot()
        out_path = step.get("out")
        if out_path:
            Path(out_path).write_bytes(base64.b64decode(b64))
            return {"path": str(out_path), "base64_length": len(b64)}
        preview = b64[:_PREVIEW_B64_CHARS] if b64 else ""
        return {
            "base64_preview": preview,
            "base64_length": len(b64),
        }

    if op == "scroll":
        pixels = int(step.get("pixels", 800))
        await bm.scroll(pixels)
        return {"scrolled": pixels}

    if op == "wait":
        selector = step.get("selector")
        timeout_ms = int(step.get("timeout_ms", 10_000))
        await bm.wait_for(selector=selector, timeout_ms=timeout_ms)
        return {"waited": True, "selector": selector}

    if op == "scroll-until":
        selector = step.get("selector")
        if not selector:
            raise ValueError("scroll-until step requires 'selector'")
        min_count = int(step.get("min_count", 1))
        scroll_px = int(step.get("pixels", 800))
        wait_ms = int(step.get("wait_ms", 2000))
        max_rounds = int(step.get("max_rounds", 20))
        rounds = 0
        while rounds < max_rounds:
            count = await bm.execute_javascript(
                f"return document.querySelectorAll({selector!r}).length"
            )
            if int(count or 0) >= min_count:
                return {"rounds": rounds, "count": count, "selector": selector}
            await bm.scroll(scroll_px)
            await bm.wait_for(timeout_ms=wait_ms)
            rounds += 1
        count = await bm.execute_javascript(
            f"return document.querySelectorAll({selector!r}).length"
        )
        return {"rounds": rounds, "count": count, "selector": selector, "exhausted": True}

    if op == "feed-posts":
        rows = await collect_raw_feed_posts_from_page(
            bm,
            max_posts=int(step.get("max_posts", 5)),
            scroll_rounds=int(step.get("scroll_rounds", 3)),
            html_selector=step.get("html_selector"),
        )
        return {"posts": rows}

    if op == "hiring-posts":
        rows = await collect_hiring_posts_from_page(
            bm,
            max_posts=int(step.get("max_posts", 10)),
            scroll_px=int(step.get("scroll_px", 800)),
            wait_ms=int(step.get("wait_ms", 2000)),
            max_scrolls=int(step.get("max_scrolls", 25)),
            plateau_limit=int(step.get("plateau_limit", 3)),
        )
        return {"posts": rows}

    if op == "check-auth":
        await bm.navigate("https://www.linkedin.com/feed/")
        authed = await is_linkedin_authenticated(bm)
        return {"authenticated": authed, "current_url": await bm.get_current_url()}

    if op == "sign-in":
        timeout_s = int(step.get("timeout_s", 120))
        authed = await wait_for_linkedin_sign_in(bm, timeout_s=timeout_s)
        return {"authenticated": authed, "timeout_s": timeout_s}

    raise ValueError(f"unknown op: {op!r}")


async def _run_command(bm: BrowserManager, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async with bm:
        for step in steps:
            op = step.get("op", "?")
            try:
                data = await _execute_step(bm, step)
                results.append({"op": op, "ok": True, "data": data})
            except Exception as exc:
                results.append({"op": op, "ok": False, "error": str(exc)})
                raise
    return results


async def _with_browser(
    bm: BrowserManager,
    command: str,
    fn: Any,
) -> Any:
    async with bm:
        return await fn(bm)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Playwright BrowserManager CLI (JSON stdout).",
    )
    _add_browser_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    p_nav = sub.add_parser("navigate", help="Navigate to URL")
    p_nav.add_argument("url")

    sub.add_parser("url", help="Print current URL")
    sub.add_parser("title", help="Print page title")

    p_text = sub.add_parser("text", help="Extract visible body text")
    p_text.add_argument("--max-chars", type=int, default=0)

    p_html = sub.add_parser("html", help="Capture page HTML")
    p_html.add_argument("--selector", default=None)
    p_html.add_argument("--max-chars", type=int, default=0)

    p_js = sub.add_parser("js", help="Execute JavaScript on the page")
    p_js.add_argument("code", nargs="?", default=None)
    p_js.add_argument("--file", default=None, help="Read JS from file")

    p_shot = sub.add_parser("screenshot", help="Capture viewport PNG")
    p_shot.add_argument("--out", default=None, help="Write PNG to path")

    p_scroll = sub.add_parser("scroll", help="Scroll vertically")
    p_scroll.add_argument("pixels", type=int)

    p_wait = sub.add_parser("wait", help="Wait for selector or timeout")
    p_wait.add_argument("--selector", default=None)
    p_wait.add_argument("--timeout-ms", type=int, default=10_000)

    p_run = sub.add_parser("run", help="Run multiple steps in one session")
    p_run.add_argument(
        "--steps",
        required=True,
        help="JSON array of step objects",
    )

    p_feed = sub.add_parser(
        "feed-posts",
        help="Collect LinkedIn feed posts as compact JSON",
    )
    p_feed.add_argument("--max-posts", type=int, default=5)
    p_feed.add_argument("--scroll-rounds", type=int, default=3)
    p_feed.add_argument("--html-selector", default=None)

    p_hiring = sub.add_parser(
        "hiring-posts",
        help="Collect LinkedIn hiring-announcement posts as structured JSON",
    )
    p_hiring.add_argument("--max-posts", type=int, default=10)
    p_hiring.add_argument("--scroll-px", type=int, default=800)
    p_hiring.add_argument("--wait-ms", type=int, default=2000)
    p_hiring.add_argument("--max-scrolls", type=int, default=25)
    p_hiring.add_argument("--plateau-limit", type=int, default=7)

    sub.add_parser(
        "check-auth",
        help="Check LinkedIn authentication for current profile",
    )
    p_sign = sub.add_parser(
        "sign-in",
        help="Open LinkedIn login and wait for manual sign-in",
    )
    p_sign.add_argument("--timeout-s", type=int, default=120)

    return parser


async def _async_main(ns: argparse.Namespace) -> int:
    try:
        bm = _browser_from_args(ns)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    cmd = ns.command

    try:
        if cmd == "navigate":

            async def _nav(b: BrowserManager) -> dict[str, Any]:
                await b.navigate(ns.url)
                return {"url": await b.get_current_url()}

            data = await _with_browser(bm, cmd, _nav)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "url":

            async def _url(b: BrowserManager) -> dict[str, Any]:
                return {"url": await b.get_current_url()}

            data = await _with_browser(bm, cmd, _url)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "title":

            async def _title(b: BrowserManager) -> dict[str, Any]:
                title = await b.get_page_title()
                url = await b.get_current_url()
                payload: dict[str, Any] = {"title": title, "url": url}
                if not title:
                    payload["hint"] = (
                        "empty_title_usually_means_a_new_browser_session_without_navigate; "
                        "chain steps with run --steps instead of separate CLI invocations"
                    )
                return payload

            data = await _with_browser(bm, cmd, _title)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "text":

            async def _text(b: BrowserManager) -> dict[str, Any]:
                text = await b.extract_visible_text()
                if ns.max_chars > 0:
                    text = _truncate_text(text, ns.max_chars)
                return {"text": text}

            data = await _with_browser(bm, cmd, _text)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "html":

            async def _html(b: BrowserManager) -> dict[str, Any]:
                html = await b.get_page_html(ns.selector)
                if ns.max_chars > 0:
                    html = _truncate_text(html, ns.max_chars)
                return {"html": html}

            data = await _with_browser(bm, cmd, _html)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "js":
            code = _read_js_code(ns)

            async def _js(b: BrowserManager) -> dict[str, Any]:
                result = await b.execute_javascript(code)
                return {"result": result}

            data = await _with_browser(bm, cmd, _js)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "screenshot":

            async def _shot(b: BrowserManager) -> dict[str, Any]:
                b64 = await b.get_screenshot()
                if not b64:
                    return {"error": "empty capture"}
                if ns.out:
                    Path(ns.out).write_bytes(base64.b64decode(b64))
                    return {"path": ns.out, "base64_length": len(b64)}
                return {
                    "base64_preview": b64[:_PREVIEW_B64_CHARS],
                    "base64_length": len(b64),
                }

            data = await _with_browser(bm, cmd, _shot)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "scroll":

            async def _scroll(b: BrowserManager) -> dict[str, Any]:
                await b.scroll(ns.pixels)
                return {"scrolled": ns.pixels}

            data = await _with_browser(bm, cmd, _scroll)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "wait":

            async def _wait(b: BrowserManager) -> dict[str, Any]:
                await b.wait_for(selector=ns.selector, timeout_ms=ns.timeout_ms)
                return {"waited": True, "selector": ns.selector}

            data = await _with_browser(bm, cmd, _wait)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "run":
            try:
                steps = json.loads(ns.steps)
            except json.JSONDecodeError as exc:
                _emit_error(cmd, f"invalid --steps JSON: {exc}")
            if not isinstance(steps, list):
                _emit_error(cmd, "--steps must be a JSON array")
            browser_echo = _browser_echo(bm)
            try:
                results = await _run_command(bm, steps)
            except Exception as exc:
                _emit_error(cmd, str(exc))
            _emit_ok(
                cmd,
                {"steps": results},
                browser_echo=browser_echo,
                session_mode="multi_step",
            )
            return 0

        if cmd == "feed-posts":

            async def _feed(b: BrowserManager) -> dict[str, Any]:
                rows = await collect_raw_feed_posts_from_page(
                    b,
                    max_posts=ns.max_posts,
                    scroll_rounds=ns.scroll_rounds,
                    html_selector=ns.html_selector,
                )
                return {"posts": rows}

            data = await _with_browser(bm, cmd, _feed)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "hiring-posts":

            async def _hiring(b: BrowserManager) -> dict[str, Any]:
                rows = await collect_hiring_posts_from_page(
                    b,
                    max_posts=ns.max_posts,
                    scroll_px=ns.scroll_px,
                    wait_ms=ns.wait_ms,
                    max_scrolls=ns.max_scrolls,
                    plateau_limit=ns.plateau_limit,
                )
                return {"posts": rows}

            data = await _with_browser(bm, cmd, _hiring)
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "check-auth":

            async def _check_auth(b: BrowserManager) -> dict[str, Any]:
                await b.navigate("https://www.linkedin.com/feed/")
                authed = await is_linkedin_authenticated(b)
                return {"authenticated": authed, "current_url": await b.get_current_url()}

            data = await _with_browser(bm, cmd, _check_auth)
            if not data["authenticated"]:
                _emit_error_payload(
                    cmd,
                    {
                        "error": "linkedin_not_authenticated",
                        "action": "invoke_skill:linkedin-sign-in",
                        "current_url": data["current_url"],
                    },
                    exit_code=1,
                )
            _emit_ok(cmd, data, browser=bm)
            return 0

        if cmd == "sign-in":

            async def _sign_in(b: BrowserManager) -> dict[str, Any]:
                authed = await wait_for_linkedin_sign_in(b, timeout_s=ns.timeout_s)
                return {
                    "authenticated": authed,
                    "timeout_s": ns.timeout_s,
                    "current_url": await b.get_current_url(),
                }

            data = await _with_browser(bm, cmd, _sign_in)
            if not data["authenticated"]:
                _emit_error_payload(
                    cmd,
                    {
                        "error": "linkedin_sign_in_timeout",
                        "timeout_s": ns.timeout_s,
                        "current_url": data["current_url"],
                    },
                    exit_code=1,
                )
            _emit_ok(cmd, data, browser=bm)
            return 0

        _emit_error("?", f"unknown command: {cmd}")
    except SystemExit:
        raise
    except Exception as exc:
        _emit_error(cmd, str(exc))
    return 1


def main() -> int:
    try:
        parser = _build_parser()
        ns = parser.parse_args()
        try:
            _parse_viewport(ns.viewport)
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 2
        return asyncio.run(_async_main(ns))
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Collect LinkedIn feed posts from a ``BrowserManager`` page via HTML parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from src.utility.linkedin_feed_parser import activity_id_from_url, parse_feed_posts

if TYPE_CHECKING:
    from src.utility.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


async def collect_raw_feed_posts_from_page(
    browser: BrowserManager,
    *,
    max_posts: int = 5,
    scroll_rounds: int = 3,
    html_selector: str | None = None,
    agent_max_posts: int | None = None,
) -> list[dict[str, str]]:
    """Scroll the feed and return compact post dicts (no raw HTML).

    ``agent_max_posts`` caps ``max_posts`` when set (LangChain agent limit).
    """
    cap = agent_max_posts if agent_max_posts is not None else max_posts
    target = max(1, min(int(max_posts), int(cap)))
    sr = max(0, min(int(scroll_rounds), 10))

    merged: list[dict[str, str]] = []
    seen: set[str] = set()

    def _key(row: dict[str, str]) -> str:
        uid = activity_id_from_url(row.get("post_url", "") or "")
        return uid or (row.get("post_url") or "")[:512]

    for i in range(sr + 1):
        html = await browser.get_page_html(html_selector)
        if not html:
            logger.warning("collect_raw_feed_posts: empty HTML")
            break
        batch = parse_feed_posts(html)
        for row in batch:
            k = _key(row)
            if k in seen:
                continue
            seen.add(k)
            merged.append(dict(row))
            if len(merged) >= target:
                break
        if len(merged) >= target:
            break
        if i < sr:
            await browser.scroll(800)
            await asyncio.sleep(0.75)

    return merged[:target]


async def collect_raw_feed_posts_json(
    browser: BrowserManager,
    **kwargs: Any,
) -> str:
    """Return JSON string of feed posts (``ensure_ascii=False``)."""
    rows = await collect_raw_feed_posts_from_page(browser, **kwargs)
    return json.dumps(rows, ensure_ascii=False)

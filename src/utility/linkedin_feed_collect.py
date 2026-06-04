"""Collect LinkedIn feed posts from a ``BrowserManager`` page via HTML parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from src.utility.linkedin_feed_parser import activity_id_from_url, parse_feed_posts

if TYPE_CHECKING:
    from src.utility.browser_manager import BrowserManager

_HIRING_JS_TEMPLATE = """
return (async () => {{
  const MIN_POSTS     = {min_posts};
  const MAX_SCROLLS   = {max_scrolls};
  const SCROLL_PX     = {scroll_px};
  const WAIT_MS       = {wait_ms};
  const PLATEAU_LIMIT = {plateau_limit};

  const HIRING_RE = /\\b(hiring|we'?re hiring|job opening|open role|apply now|now hiring|looking for a|seeking a|join (?:our|the) team|open position|new role|job opportunit)\\b/i;
  const POST_URL_RE = /linkedin\\.com\\/(posts\\/[^?#"'\\s]+_activity|feed\\/update\\/)/;

  const feed = document.querySelector("div[data-testid=mainFeed]");
  if (!feed) return {{ error: "no feed" }};

  const seen = new Set();
  const results = [];
  let scrollStuck = 0;
  const ws = document.querySelector("#workspace") || document.documentElement;

  function postContainers() {{
    return [...feed.querySelectorAll(":scope > div[data-display-contents='true']")]
      .filter(c => c.querySelector("a[href]"));
  }}

  function extractPost(card) {{
    const hrefs = [...card.querySelectorAll("a[href]")].map(a => a.href);
    const companyUrls = [...new Set(
      hrefs.filter(h => {{
        try {{ return /^\\/company\\/[^/]+\\/?$/.test(new URL(h).pathname); }}
        catch {{ return false; }}
      }})
    )];
    const jobUrls   = [...new Set(hrefs.filter(h => /\\/jobs\\/view\\//.test(h)))];
    const authorUrl = hrefs.find(h => /linkedin\\.com\\/in\\//.test(h)) || null;
    const postUrl   = hrefs.find(h => POST_URL_RE.test(h)) || null;
    const text      = card.innerText || "";
    const isHiring  = jobUrls.length > 0 || HIRING_RE.test(text);
    if (!isHiring || !authorUrl) return null;
    const key = postUrl || authorUrl;
    if (seen.has(key)) return null;
    seen.add(key);
    return {{ company_urls: companyUrls, job_listing_urls: jobUrls, author_profile_url: authorUrl, post_url: postUrl }};
  }}

  for (let i = 0; i < MAX_SCROLLS; i++) {{
    for (const card of postContainers()) {{
      const entry = extractPost(card);
      if (entry) results.push(entry);
    }}
    if (results.length >= MIN_POSTS) break;
    const scrollBefore = ws.scrollTop;
    ws.scrollBy(0, SCROLL_PX);
    await new Promise(r => setTimeout(r, WAIT_MS));
    if (ws.scrollTop === scrollBefore) {{
      scrollStuck++;
      if (scrollStuck >= PLATEAU_LIMIT) break;
    }} else {{
      scrollStuck = 0;
    }}
  }}

  return results;
}})();
"""

logger = logging.getLogger(__name__)

_MAX_SCROLL_CAP = 30
_PLATEAU_ROUNDS = 2
_SCROLL_PIXELS = 800
_SCROLL_PAUSE_S = 0.75


def _scroll_budget(*, scroll_rounds: int, target: int) -> int:
    """Max scroll iterations allowed before giving up (0 = parse current viewport only)."""
    sr = int(scroll_rounds)
    if sr <= 0:
        return 0
    return min(max(sr, target), _MAX_SCROLL_CAP)


async def collect_raw_feed_posts_from_page(
    browser: BrowserManager,
    *,
    max_posts: int = 5,
    scroll_rounds: int = 3,
    html_selector: str | None = None,
    agent_max_posts: int | None = None,
) -> list[dict[str, str]]:
    """Scroll the feed and return compact post dicts (no raw HTML).

    Keeps scrolling down on the current page until ``max_posts`` unique posts are
    collected, the feed stops yielding new posts, or the scroll budget is exhausted.
    Callers should not re-navigate to load more — increase ``scroll_rounds`` or call
    ``browser.scroll`` first, then invoke this again on the same session.

    ``agent_max_posts`` caps ``max_posts`` when set (LangChain agent limit).
    """
    cap = agent_max_posts if agent_max_posts is not None else max_posts
    target = max(1, min(int(max_posts), int(cap)))
    max_scrolls = _scroll_budget(scroll_rounds=scroll_rounds, target=target)

    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    plateau = 0
    scroll_count = 0

    def _key(row: dict[str, str]) -> str:
        uid = activity_id_from_url(row.get("post_url", "") or "")
        if uid:
            return f"activity:{uid}"
        post = (row.get("post_url") or "").split("?", 1)[0]
        if post:
            return post[:512]
        author = row.get("author_profile_url") or ""
        return f"author:{author}" if author else ""

    while True:
        html = await browser.get_page_html(html_selector)
        if not html:
            logger.warning("collect_raw_feed_posts: empty HTML")
            break

        prev_len = len(merged)
        batch = parse_feed_posts(html)
        for row in batch:
            k = _key(row)
            if not k or k in seen:
                continue
            seen.add(k)
            merged.append(dict(row))
            if len(merged) >= target:
                break

        if len(merged) >= target:
            break

        if len(merged) == prev_len:
            plateau += 1
        else:
            plateau = 0

        if plateau >= _PLATEAU_ROUNDS:
            logger.info(
                "collect_raw_feed_posts: feed plateau after %d scrolls (%d/%d posts)",
                scroll_count,
                len(merged),
                target,
            )
            break

        if scroll_count >= max_scrolls:
            logger.info(
                "collect_raw_feed_posts: scroll budget exhausted (%d/%d posts)",
                len(merged),
                target,
            )
            break

        await browser.scroll(_SCROLL_PIXELS)
        scroll_count += 1
        await asyncio.sleep(_SCROLL_PAUSE_S)

    return merged[:target]


async def collect_raw_feed_posts_json(
    browser: BrowserManager,
    **kwargs: Any,
) -> str:
    """Return JSON string of feed posts (``ensure_ascii=False``)."""
    rows = await collect_raw_feed_posts_from_page(browser, **kwargs)
    return json.dumps(rows, ensure_ascii=False)


async def collect_hiring_posts_from_page(
    browser: BrowserManager,
    *,
    max_posts: int = 10,
    scroll_px: int = 800,
    wait_ms: int = 2000,
    max_scrolls: int = 25,
    plateau_limit: int = 7,
) -> list[dict[str, Any]]:
    """Scroll the LinkedIn feed and return hiring-announcement posts.

    Runs a self-contained JS IIFE in the browser that scrolls and collects posts
    until ``max_posts`` hiring entries are found, ``max_scrolls`` is exhausted, or
    ``plateau_limit`` consecutive scroll rounds yield no new entries.

    Entries without an identifiable author (``author_profile_url`` is null) are
    dropped — they are typically ads with unreliable dedup keys.

    Each entry: ``company_urls``, ``job_listing_urls``, ``author_profile_url``, ``post_url``.
    """
    js = _HIRING_JS_TEMPLATE.format(
        min_posts=max(1, int(max_posts)),
        max_scrolls=max(1, int(max_scrolls)),
        scroll_px=max(1, int(scroll_px)),
        wait_ms=max(100, int(wait_ms)),
        plateau_limit=max(1, int(plateau_limit)),
    )
    result = await browser.execute_javascript(js)
    if isinstance(result, dict) and result.get("error"):
        logger.warning("collect_hiring_posts: JS error: %s", result["error"])
        return []
    if not isinstance(result, list):
        logger.warning("collect_hiring_posts: unexpected JS result type: %s", type(result))
        return []
    return result

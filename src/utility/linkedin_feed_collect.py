"""Collect LinkedIn feed posts from a ``BrowserManager`` page via HTML parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.utility.linkedin_feed_parser import (
    DEFAULT_POST_CARD_SELECTOR,
    parse_feed_posts,
    post_dedupe_id_from_url,
)

LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_FEED_RECENT_URL = "https://www.linkedin.com/feed/?feedType=recent"
DEFAULT_SORT_JS_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "linkedin-job-search"
    / "examples"
    / "linkedin_sort_recent.js"
)
SORT_SETTLE_MS = 2000

if TYPE_CHECKING:
    from playwright.async_api import Page

    from src.utility.browser_manager import BrowserManager

_HIRING_JS_TEMPLATE = """
return (async () => {{
  const MIN_POSTS     = {min_posts};
  const MAX_SCROLLS   = {max_scrolls};
  const SCROLL_PX     = {scroll_px};
  const WAIT_MS       = {wait_ms};
  const PLATEAU_LIMIT = {plateau_limit};

  const HIRING_RE = /\\b(hiring|we'?re hiring|we\\s+are\\s+hiring|job opening|open role|apply(?:\\s+now| today)?|now hiring|looking for|seeking|join (?:our|the) team|open position|new role|job opportunit(?:y|ies)|recruiting|recruiter|vacancy|vacancies|career opportunity|job alert|accepting applications?|applications?\\s+(?:open|welcome|accepted?)|we(?:'re|\\s+are)\\s+looking|immediate opening|talent acquisition)\\b/i;
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

# In-browser feed extraction. LinkedIn's current DOM uses ``div[data-lazy-mount-id]``
# cards instead of legacy ``div[data-display-contents='true']`` children of mainFeed.
# postContainers() tries legacy first, then lazy-mount; extractPost keeps author-only
# stubs (no post_url yet) so Python can resolve URLs via Send → Copy link.
_FEED_POSTS_JS_TEMPLATE = """
return (async () => {{
  const MIN_POSTS     = {min_posts};
  const MAX_SCROLLS   = {max_scrolls};
  const SCROLL_PX     = {scroll_px};
  const WAIT_MS       = {wait_ms};
  const PLATEAU_LIMIT = {plateau_limit};

  const POST_HREF_RE = /linkedin\\.com\\/(feed\\/update\\/|posts\\/)/;
  const URN_IN_STR_RE = /urn:li:(activity|share|ugcPost):\\d+/i;
  const URN_EXACT_RE = /^urn:li:(activity|share|ugcPost):\\d+$/i;

  const feedRoot = document.querySelector("div[data-testid=mainFeed]");
  const lazyCards = document.querySelectorAll("div[data-lazy-mount-id]");
  if (!feedRoot && !lazyCards.length) return {{ error: "no feed" }};
  const feed = feedRoot || document.querySelector("#workspace") || document.documentElement;

  const seen = new Set();
  const results = [];
  let scrollStuck = 0;
  const ws = document.querySelector("#workspace") || document.documentElement;

  function urnToFeedUrl(urn) {{
    const m = String(urn).match(URN_IN_STR_RE);
    if (!m) return null;
    return `https://www.linkedin.com/feed/update/${{m[0]}}/`;
  }}

  function findPostUrl(card) {{
    for (const a of card.querySelectorAll("a[href]")) {{
      const href = (a.href || "").split("?")[0];
      if (POST_HREF_RE.test(href)) return href;
    }}
    for (const el of card.querySelectorAll("*")) {{
      for (const attr of ["data-urn", "data-activity-urn"]) {{
        const raw = el.getAttribute(attr);
        if (!raw) continue;
        if (URN_EXACT_RE.test(raw)) {{
          const url = urnToFeedUrl(raw);
          if (url) return url;
        }}
        const embedded = raw.match(URN_IN_STR_RE);
        if (embedded) {{
          const url = urnToFeedUrl(embedded[0]);
          if (url) return url;
        }}
      }}
    }}
    return null;
  }}

  function postContainers() {{
    const legacy = feedRoot
      ? [...feedRoot.querySelectorAll(":scope > div[data-display-contents='true']")]
          .filter(c => c.querySelector("a[href], [data-urn], [data-activity-urn]"))
      : [];
    if (legacy.length) return legacy;
    const scope = feedRoot || document;
    return [...scope.querySelectorAll("div[data-lazy-mount-id]")]
      .filter(c => c.querySelector("a[href], [data-urn], [data-activity-urn]"));
  }}

  function extractPost(card) {{
    const postUrl = findPostUrl(card) || "";
    const hrefs = [...card.querySelectorAll("a[href]")].map(a => a.href);
    const authorUrl = hrefs.find(h =>
      /linkedin\\.com\\/in\\//.test(h) && !/\\/company\\//.test(h)
    ) || "";
    if (!postUrl && !authorUrl) return null;
    let text = (card.innerText || "").replace(/\\s+/g, " ").trim();
    if (text.length > 400) text = text.slice(0, 400) + "\\u2026";
    const timeEl = card.querySelector("time");
    const relTime = timeEl
      ? (timeEl.getAttribute("datetime") || timeEl.innerText || "").slice(0, 120)
      : "";
    const key = postUrl ? postUrl.split("?")[0] : `author:${{authorUrl}}`;
    if (seen.has(key)) return null;
    seen.add(key);
    return {{
      post_url: postUrl,
      author_profile_url: authorUrl,
      text_snippet: text,
      relative_time: relTime,
    }};
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

_CLIPBOARD_SPY_JS = """
if (!window.__clipboardSpyInstalled) {
    window.__clipboardLastUrl = null;
    window.__resolvedCardIds = new Set();
    document.addEventListener('copy', (e) => {
        const txt = e.clipboardData && e.clipboardData.getData('text/plain');
        if (txt) window.__clipboardLastUrl = txt;
    }, true);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        const _orig = navigator.clipboard.writeText.bind(navigator.clipboard);
        navigator.clipboard.writeText = async (t) => { window.__clipboardLastUrl = t; return _orig(t).catch(() => {}); };
    }
    window.__clipboardSpyInstalled = true;
}
"""

_FIND_SEND_BTN_JS = """
(authorHref) => {
    const feed = document.querySelector("div[data-testid=mainFeed]") || document;
    const anchors = [...feed.querySelectorAll("a[href]")];
    const match = anchors.find(a => a.href && (a.href === authorHref || a.href.startsWith(authorHref)));
    if (!match) return false;
    const card = match.closest("div[data-lazy-mount-id]");
    if (card) {
        const cardId = card.getAttribute("data-lazy-mount-id");
        if (cardId && window.__resolvedCardIds && window.__resolvedCardIds.has(cardId)) return false;
    }
    let node = match.parentElement;
    for (let i = 0; i < 25; i++) {
        if (!node || node === document.body) break;
        const elems = [...node.querySelectorAll("button, a")];
        const sendBtn = elems.find(b => {
            const label = (b.getAttribute("aria-label") || "").toLowerCase();
            const text = (b.innerText || b.textContent || "").trim().toLowerCase();
            return /\\bsend\\b/.test(label) || text === "send";
        });
        if (sendBtn) {
            const firstInLink = node.querySelector("a[href*='/in/']");
            if (!firstInLink || !firstInLink.href.startsWith(authorHref)) return false;
            window.__lastClickedCardId = (card && card.getAttribute("data-lazy-mount-id")) || null;
            sendBtn.click();
            return true;
        }
        node = node.parentElement;
    }
    return false;
}
"""

_MARK_CARD_RESOLVED_JS = "(cardId) => { if (window.__resolvedCardIds && cardId) window.__resolvedCardIds.add(cardId); }"


async def prepare_live_feed_page(
    browser: "BrowserManager",
    *,
    sort_js_path: str | Path | None = None,
    post_card_selector: str | None = DEFAULT_POST_CARD_SELECTOR,
) -> dict[str, Any]:
    """Navigate, wait for hydration, sort Recent, settle, then wait for feed cards.

    Shared by :class:`LinkedInFeedAgent` and the A/B control arm so production
    and experiments use the same ordering + lazy-mount hydration sequence.
    Falls back to ``?feedType=recent`` when the sort-menu JS cannot click Recent.
    """
    await browser.navigate(LINKEDIN_FEED_URL)
    try:
        await browser.wait_for(
            selector="div[data-testid=mainFeed], div[data-lazy-mount-id]",
            timeout_ms=60_000,
        )
    except Exception as exc:
        logger.warning("Live feed container wait failed: %s", exc)

    sort_applied = False
    sort_method = "none"
    sort_path = Path(sort_js_path or DEFAULT_SORT_JS_PATH)
    if sort_path.is_file():
        result = await browser.execute_javascript(sort_path.read_text(encoding="utf-8"))
        if isinstance(result, dict) and result.get("sorted"):
            sort_applied = True
            sort_method = str(result.get("method") or "menu")

    if not sort_applied:
        logger.info("Sort menu failed; navigating to Recent feed URL fallback")
        await browser.navigate(LINKEDIN_FEED_RECENT_URL)
        sort_method = "feedType=recent"
        sort_applied = True

    await browser.wait_for(timeout_ms=SORT_SETTLE_MS)

    if post_card_selector:
        try:
            await browser.wait_for(selector=post_card_selector, timeout_ms=15_000)
        except Exception:
            pass

    return {"sort_applied": sort_applied, "sort_method": sort_method}


async def _resolve_author_only_rows(
    page: "Page",
    rows: list[dict[str, str]],
) -> int:
    """Fill missing ``post_url`` via Send → Copy link; return count resolved.

    Lazy-mount cards often expose ``author_profile_url`` before a stable post href
    or ``data-urn`` is present in the live DOM.
    """
    resolved = 0
    for entry in rows:
        if entry.get("post_url") or not entry.get("author_profile_url"):
            continue
        url = await _resolve_one_post_url(page, entry["author_profile_url"])
        if url:
            entry["post_url"] = url
            resolved += 1
    return resolved


async def _resolve_one_post_url(
    page: "Page",
    author_url: str,
    *,
    menu_timeout_ms: int = 3000,
    pause_s: float = 0.5,
) -> str | None:
    """Click Send → Copy link to post for one post; return the URL or None."""
    await page.evaluate("window.__clipboardLastUrl = null")
    clicked = await page.evaluate(_FIND_SEND_BTN_JS, author_url)
    if not clicked:
        return None
    try:
        await page.wait_for_selector("text=Copy link to post", timeout=menu_timeout_ms)
        await page.locator("text=Copy link to post").first.click(timeout=2000)
    except Exception:
        await page.keyboard.press("Escape")
        return None
    await asyncio.sleep(pause_s)
    url = await page.evaluate("window.__clipboardLastUrl")
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.2)
    if url and isinstance(url, str) and "linkedin.com" in url:
        card_id = await page.evaluate("() => window.__lastClickedCardId || null")
        if card_id:
            await page.evaluate(_MARK_CARD_RESOLVED_JS, card_id)
        return url
    return None


_MAX_SCROLL_CAP = 30
_PLATEAU_ROUNDS = 5
_SCROLL_PIXELS = 800
_SCROLL_PAUSE_S = 0.75


def _scroll_budget(*, scroll_rounds: int, target: int) -> int:
    """Max scroll iterations allowed before giving up (0 = parse current viewport only)."""
    sr = int(scroll_rounds)
    if sr <= 0:
        return 0
    return min(max(sr, target), _MAX_SCROLL_CAP)


def _row_dedupe_key(row: dict[str, str]) -> str:
    post_url = row.get("post_url") or ""
    urn_id = post_dedupe_id_from_url(post_url)
    if urn_id:
        return f"urn:{urn_id}"
    post = post_url.split("?", 1)[0]
    if post:
        return post[:512]
    author = row.get("author_profile_url") or ""
    return f"author:{author}" if author else ""


async def _collect_feed_posts_via_js(
    browser: BrowserManager,
    *,
    max_posts: int,
    scroll_rounds: int,
    scroll_px: int = _SCROLL_PIXELS,
    wait_ms: int = 750,
    plateau_limit: int = _PLATEAU_ROUNDS,
) -> list[dict[str, str]] | None:
    """In-browser feed extraction (scroll + URN/href). Returns None when feed missing."""
    max_scrolls = _scroll_budget(scroll_rounds=scroll_rounds, target=max_posts)
    if max_scrolls <= 0:
        max_scrolls = 1
    js = _FEED_POSTS_JS_TEMPLATE.format(
        min_posts=max(1, int(max_posts)),
        max_scrolls=max_scrolls,
        scroll_px=max(1, int(scroll_px)),
        wait_ms=max(100, int(wait_ms)),
        plateau_limit=max(1, int(plateau_limit)),
    )
    result = await browser.execute_javascript(js)
    if isinstance(result, dict) and result.get("error"):
        logger.warning("collect_raw_feed_posts: JS error: %s", result["error"])
        return None
    if not isinstance(result, list):
        logger.warning(
            "collect_raw_feed_posts: unexpected JS result type: %s", type(result)
        )
        return None
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in result:
        if not isinstance(item, dict):
            continue
        row = {
            "post_url": str(item.get("post_url") or ""),
            "author_profile_url": str(item.get("author_profile_url") or ""),
            "text_snippet": str(item.get("text_snippet") or ""),
            "relative_time": str(item.get("relative_time") or ""),
        }
        # Keep author-only stubs from JS (post_url filled later via Send button).
        if not row["post_url"] and not row["author_profile_url"]:
            continue
        key = _row_dedupe_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows[: max(1, int(max_posts))]


async def collect_raw_feed_posts_from_page(
    browser: BrowserManager,
    *,
    max_posts: int = 5,
    scroll_rounds: int = 3,
    html_selector: str | None = None,
    post_card_selector: str | None = DEFAULT_POST_CARD_SELECTOR,
    agent_max_posts: int | None = None,
    resolve_missing_urls: bool = True,
) -> list[dict[str, str]]:
    """Scroll the feed and return compact post dicts (no raw HTML).

    Keeps scrolling down on the current page until ``max_posts`` unique posts are
    collected, the feed stops yielding new posts, or the scroll budget is exhausted.
    Callers should not re-navigate to load more — increase ``scroll_rounds`` or call
    ``browser.scroll`` first, then invoke this again on the same session.

    ``agent_max_posts`` caps ``max_posts`` when set (LangChain agent limit).

    Prefers in-browser JS extraction (``data-urn`` / post hrefs on feed cards).
    Falls back to HTML parsing when the feed container is missing from the DOM.
    """
    cap = agent_max_posts if agent_max_posts is not None else max_posts
    target = max(1, min(int(max_posts), int(cap)))

    js_rows = await _collect_feed_posts_via_js(
        browser,
        max_posts=target,
        scroll_rounds=scroll_rounds,
    )
    # Non-empty list (including author-only stubs) — resolve URLs on the live page.
    # Empty list or JS error (``None``) falls through to HTML parse + scroll loop.
    if js_rows:
        if resolve_missing_urls:
            page = browser._ensure_started()
            await page.evaluate(_CLIPBOARD_SPY_JS)
            await _resolve_author_only_rows(page, js_rows)
        return js_rows[:target]

    max_scrolls = _scroll_budget(scroll_rounds=scroll_rounds, target=target)

    page = browser._ensure_started()
    if resolve_missing_urls:
        await page.evaluate(_CLIPBOARD_SPY_JS)

    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    plateau = 0
    scroll_count = 0

    while True:
        html = await browser.get_page_html(html_selector)
        if not html:
            logger.warning("collect_raw_feed_posts: empty HTML")
            break

        prev_len = len(merged)
        batch = parse_feed_posts(html, post_card_selector=post_card_selector)
        for row in batch:
            k = _row_dedupe_key(row)
            if not k or k in seen:
                continue
            seen.add(k)
            entry = dict(row)
            if (
                resolve_missing_urls
                and not entry.get("post_url")
                and entry.get("author_profile_url")
            ):
                resolved = await _resolve_one_post_url(page, entry["author_profile_url"])
                if resolved:
                    entry["post_url"] = resolved
                    seen.discard(k)
                    new_k = _row_dedupe_key(entry)
                    if new_k and new_k != k:
                        if new_k in seen:
                            continue
                        seen.add(new_k)
                    else:
                        seen.add(k)
            merged.append(entry)
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


_RESOLVE_SCROLL_STEP = 600
_RESOLVE_SCROLL_ATTEMPTS = 8


async def resolve_post_urls_via_send_button(
    browser: "BrowserManager",
    posts: list[dict[str, Any]],
    *,
    menu_timeout_ms: int = 3000,
    pause_s: float = 0.5,
    scroll_step: int = _RESOLVE_SCROLL_STEP,
    max_attempt_per_post: int = _RESOLVE_SCROLL_ATTEMPTS,
) -> list[dict[str, Any]]:
    """Fill in null ``post_url`` entries by clicking Send → Copy link to post.

    Scrolls back to the top of the feed before starting, then advances forward
    one card at a time so each post is in the viewport when its Send button is
    clicked.  A ``resolved_urls`` set guards against the same card being
    selected for multiple author-URL queries (e.g. when the author appears as
    an @mention or reposter in a different visible card).
    """
    page = browser._ensure_started()
    await page.evaluate(_CLIPBOARD_SPY_JS)

    # Return to feed top so posts that the IIFE scrolled past re-enter the DOM.
    await page.evaluate(
        "(document.querySelector('#workspace') || document.documentElement).scrollTop = 0"
    )
    await asyncio.sleep(1.0)

    resolved_urls: set[str] = set()
    for post in posts:
        if post.get("post_url"):
            resolved_urls.add(post["post_url"])
            continue
        author_url = post.get("author_profile_url")
        if not author_url:
            continue

        url: str | None = None
        for _ in range(max_attempt_per_post):
            candidate = await _resolve_one_post_url(
                page, author_url, menu_timeout_ms=menu_timeout_ms, pause_s=pause_s
            )
            if candidate and candidate not in resolved_urls:
                url = candidate
                break
            await browser.scroll(scroll_step)
            await asyncio.sleep(0.5)

        if url:
            post["post_url"] = url
            resolved_urls.add(url)

    return posts


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
        logger.warning(
            "collect_hiring_posts: unexpected JS result type: %s", type(result))
        return []
    return result

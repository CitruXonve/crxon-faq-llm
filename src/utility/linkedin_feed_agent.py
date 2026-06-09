"""Deterministic LinkedIn feed collection for production/background use.

Production-oriented sibling of :class:`LinkedInWebAgent` — no LLM, no token
usage. Scrapes raw feed posts for background jobs, cron, or downstream
orchestration.

Default path (``use_crawl4ai=False``): one live ``BrowserManager`` session —
hydrate feed → sort Recent → scroll → extract lazy-mount cards → inline
Send → Copy link for author-only stubs.

Opt-in Crawl4AI (``use_crawl4ai=True``): virtual-scroll HTML snapshot for A/B
or experimentation. Crawl4AI often returns an unhydrated shell; enable
``resolve_missing_urls`` to fall back to the live session when the crawl is empty.

Constraints:

- Uses ``linkedin_profile_lock`` under ``user_data_dir``. Do not run
  ``LinkedInFeedAgent``, ``LinkedInWebAgent``, or ``browser_manager.py``
  concurrently against the same profile.
- Headless runs require a pre-warmed signed-in profile (``make sign-in-linkedin``).
- Integrate as a background worker, not inline in FastAPI request handlers.
- Feed cards use ``post_card_selector`` (default ``div[data-lazy-mount-id]``).
- ``resolve_missing_urls=False`` skips Send → Copy link (degraded; may yield
  author-only rows without ``post_url``).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.config.settings import settings
from src.utility.browser_manager import BrowserManager
from src.utility.crawl4ai_linkedin_helper import (
    CrawlFeedResult,
    LINKEDIN_FEED_URL,
    crawl_linkedin_feed,
    dedupe_feed_posts,
    linkedin_profile_lock,
)
from src.utility.linkedin_auth import is_linkedin_authenticated
from src.utility.linkedin_feed_collect import (
    collect_raw_feed_posts_from_page,
    prepare_live_feed_page,
    resolve_post_urls_via_send_button,
)
from src.utility.linkedin_feed_parser import (
    DEFAULT_POST_CARD_SELECTOR,
    post_url_validation_reason,
)
from src.utility.spinner import make_progress_emitter

logger = logging.getLogger(__name__)

_MAX_INVALID_SAMPLES = 5


def _format_duration(total_seconds: float) -> str:
    """Format a duration as 'Xm Y.YYs' (always shows minutes, even when 0)."""
    minutes, seconds = divmod(total_seconds, 60)
    return f"{int(minutes)}m {int(seconds)}s"


def default_export_path(export_dir: str | Path | None = None) -> Path:
    """Timestamped export path under the export directory."""
    base = Path(export_dir or settings.EXPORT_DIRECTORY)
    stamp = datetime.now(ZoneInfo("US/Pacific")
                         ).strftime("%Y-%m-%dT%H:%M:%S%z")
    return base / f"linkedin_feed_{stamp}.json"


def _public_quality(q: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_count": q["total_count"],
        "valid_post_url_count": q["valid_post_url_count"],
        "valid_post_url_ratio": q["valid_post_url_ratio"],
        "empty_post_url_count": q["empty_post_url_count"],
        "invalid_post_url_samples": q["invalid_post_url_samples"],
    }


def write_feed_export(
    path: str | Path,
    *,
    posts: list[dict[str, Any]],
    valid_posts: list[dict[str, Any]],
    quality: dict[str, Any],
    params: dict[str, Any],
) -> Path:
    """Write feed collection JSON to ``path``."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": params,
        "posts": posts,
        "valid_posts": valid_posts,
        "quality": quality,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return out


def arm_quality_metrics(
    posts: list[dict[str, Any]],
    *,
    require_activity_id: bool = False,
) -> dict[str, Any]:
    """Compute valid ``post_url`` stats for one arm."""
    total = len(posts)
    valid_rows: list[dict[str, Any]] = []
    invalid_samples: list[dict[str, str]] = []
    empty_count = 0

    for row in posts:
        url = (row.get("post_url") or "").strip()
        if not url:
            empty_count += 1
        reason = post_url_validation_reason(
            url, require_activity_id=require_activity_id
        )
        if reason is None:
            valid_rows.append(row)
        elif len(invalid_samples) < _MAX_INVALID_SAMPLES:
            invalid_samples.append(
                {
                    "post_url": url,
                    "author_profile_url": row.get("author_profile_url") or "",
                    "reason": reason,
                }
            )

    valid_count = len(valid_rows)
    ratio = (valid_count / total) if total else 0.0
    return {
        "total_count": total,
        "valid_post_url_count": valid_count,
        "valid_post_url_ratio": round(ratio, 4),
        "empty_post_url_count": empty_count,
        "invalid_post_url_samples": invalid_samples,
        "valid_rows": valid_rows,
    }


class LinkedInFeedAgent:
    """LinkedIn feed scraper — live BrowserManager by default, Crawl4AI opt-in."""

    def __init__(
        self,
        user_data_dir: str | Path = ".browser_profile",
        profile_directory: str | None = "Default",
        headless: bool = True,
        max_posts: int = 25,
        scroll_rounds: int = 10,
        container_selector: str = "#workspace",
        post_card_selector: str | None = DEFAULT_POST_CARD_SELECTOR,
        viewport: tuple[int, int] = (1280, 720),
        export_dir: str | None = None,
        require_activity_id: bool = False,
        login_timeout_s: int = 120,
        check_auth: bool = True,
        sort_js_path: str | Path | None = None,
        resolve_missing_urls: bool = True,
        use_crawl4ai: bool = False,
    ) -> None:
        self.user_data_dir = Path(user_data_dir)
        self.profile_directory = profile_directory
        self.headless = headless
        self.max_posts = max_posts
        self.scroll_rounds = scroll_rounds
        self.container_selector = container_selector
        self.post_card_selector = post_card_selector
        self.viewport = viewport
        self.require_activity_id = require_activity_id
        self.login_timeout_s = login_timeout_s
        self.check_auth = check_auth
        self.sort_js_path = sort_js_path
        self.resolve_missing_urls = resolve_missing_urls
        self.use_crawl4ai = use_crawl4ai
        self._export_dir = export_dir or settings.EXPORT_DIRECTORY

    async def run(
        self,
        *,
        on_progress: Callable[[str], None] | None = None,
        write_export: bool = True,
        export_filename: str | None = None,
    ) -> dict[str, Any]:
        """Collect feed posts once and return a summary dict."""
        emit = make_progress_emitter(on_progress)
        start = time.perf_counter()

        if self.check_auth:
            await self._ensure_authenticated(emit)

        crawl_result: CrawlFeedResult | None = None
        collection_mode = "live"
        sort_meta: dict[str, Any] = {
            "sort_applied": False, "sort_method": "none"}
        urls_resolved_count = 0
        browser_fallback_used = False
        posts: list[dict[str, Any]] = []

        if self.use_crawl4ai:
            emit("collecting feed (crawl4ai)")
            collection_mode = "crawl4ai"
            crawl_result = await crawl_linkedin_feed(
                user_data_dir=self.user_data_dir,
                profile_directory=self.profile_directory,
                max_posts=self.max_posts,
                scroll_rounds=self.scroll_rounds,
                headless=self.headless,
                sort_js_path=self.sort_js_path,
                container_selector=self.container_selector,
                post_card_selector=self.post_card_selector,
                viewport=self.viewport,
            )
            posts = list(crawl_result.posts)
            if self.resolve_missing_urls:
                if not posts:
                    emit("collecting feed live")
                    posts, sort_meta = await self._collect_feed_live()
                    collection_mode = "crawl4ai+live_fallback"
                    browser_fallback_used = True
                    urls_resolved_count = sum(
                        1 for p in posts if (p.get("post_url") or "").strip()
                    )
                else:
                    urls_resolved_count = await self._resolve_missing_post_urls(
                        posts, emit
                    )
            posts = dedupe_feed_posts(posts, max_posts=self.max_posts)
        else:
            emit("collecting feed")
            posts, sort_meta = await self._collect_feed_live()
            urls_resolved_count = sum(
                1 for p in posts if (p.get("post_url") or "").strip()
            )
            posts = dedupe_feed_posts(posts, max_posts=self.max_posts)

        emit("validating posts")
        quality_raw = arm_quality_metrics(
            posts,
            require_activity_id=self.require_activity_id,
        )
        valid_posts = quality_raw["valid_rows"]
        quality = _public_quality(quality_raw)

        export_path: str | None = None
        if write_export:
            emit("writing export")
            out_path = (
                Path(self._export_dir) / export_filename
                if export_filename
                else default_export_path(self._export_dir)
            )
            params = {
                "user_data_dir": str(self.user_data_dir),
                "profile_directory": self.profile_directory,
                "headless": self.headless,
                "max_posts": self.max_posts,
                "scroll_rounds": self.scroll_rounds,
                "container_selector": self.container_selector,
                "post_card_selector": self.post_card_selector,
                "require_activity_id": self.require_activity_id,
                "resolve_missing_urls": self.resolve_missing_urls,
                "use_crawl4ai": self.use_crawl4ai,
                "collection_mode": collection_mode,
                "sort_applied": sort_meta.get("sort_applied", False),
                "sort_method": sort_meta.get("sort_method", "none"),
                "urls_resolved_count": urls_resolved_count,
                "browser_fallback_used": browser_fallback_used,
            }
            written = write_feed_export(
                out_path,
                posts=posts,
                valid_posts=valid_posts,
                quality=quality,
                params=params,
            )
            export_path = str(written)

        elapsed_seconds = time.perf_counter() - start
        elapsed_pretty = _format_duration(elapsed_seconds)
        ok = quality["valid_post_url_count"] > 0
        crawl_ok = crawl_result.crawl4ai_success if crawl_result else None

        logger.info(
            "LinkedInFeedAgent run complete in %s — mode=%s posts=%d valid=%d",
            elapsed_pretty,
            collection_mode,
            len(posts),
            quality["valid_post_url_count"],
        )

        return {
            "ok": ok,
            "posts": posts,
            "valid_posts": valid_posts,
            "quality": quality,
            "elapsed_seconds": elapsed_seconds,
            "elapsed_pretty": elapsed_pretty,
            "export_path": export_path,
            "crawl4ai_success": crawl_ok,
            "error_message": crawl_result.error_message if crawl_result else None,
            "urls_resolved_count": urls_resolved_count,
            "resolve_missing_urls": self.resolve_missing_urls,
            "use_crawl4ai": self.use_crawl4ai,
            "collection_mode": collection_mode,
            "sort_applied": sort_meta.get("sort_applied", False),
            "sort_method": sort_meta.get("sort_method", "none"),
            "browser_fallback_used": browser_fallback_used,
        }

    async def _collect_feed_live(
        self,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Single BrowserManager session: prepare feed page, scroll, collect, resolve."""
        bm = BrowserManager(
            headless=self.headless,
            viewport=self.viewport,
            user_data_dir=self.user_data_dir,
            profile_directory=self.profile_directory,
        )
        async with linkedin_profile_lock(self.user_data_dir):
            async with bm:
                sort_meta = await prepare_live_feed_page(
                    bm,
                    sort_js_path=self.sort_js_path,
                    post_card_selector=self.post_card_selector,
                )
                rows = await collect_raw_feed_posts_from_page(
                    bm,
                    max_posts=self.max_posts,
                    scroll_rounds=self.scroll_rounds,
                    post_card_selector=self.post_card_selector,
                    resolve_missing_urls=self.resolve_missing_urls,
                )
                return rows, sort_meta

    async def _resolve_missing_post_urls(
        self,
        posts: list[dict[str, Any]],
        emit: Callable[[str], None],
    ) -> int:
        """Fill missing ``post_url`` via Send → Copy link (Crawl4AI partial rows only)."""
        candidates = [
            p
            for p in posts
            if not (p.get("post_url") or "").strip()
            and (p.get("author_profile_url") or "").strip()
        ]
        if not candidates:
            return 0

        before = sum(1 for p in posts if (p.get("post_url") or "").strip())
        emit("resolving post urls")
        bm = BrowserManager(
            headless=self.headless,
            viewport=self.viewport,
            user_data_dir=self.user_data_dir,
            profile_directory=self.profile_directory,
        )
        async with linkedin_profile_lock(self.user_data_dir):
            async with bm:
                await prepare_live_feed_page(
                    bm,
                    sort_js_path=self.sort_js_path,
                    post_card_selector=self.post_card_selector,
                )
                await resolve_post_urls_via_send_button(bm, posts)

        after = sum(1 for p in posts if (p.get("post_url") or "").strip())
        resolved = after - before
        if resolved:
            logger.info(
                "Resolved %d post URL(s) via Send → Copy link", resolved)
        return resolved

    async def _ensure_authenticated(
        self,
        emit: Callable[[str], None],
    ) -> None:
        emit("checking auth")
        bm = BrowserManager(
            headless=self.headless,
            viewport=self.viewport,
            user_data_dir=self.user_data_dir,
            profile_directory=self.profile_directory,
        )
        async with linkedin_profile_lock(self.user_data_dir):
            async with bm:
                await bm.navigate(LINKEDIN_FEED_URL)
                if await is_linkedin_authenticated(bm):
                    logger.info("LinkedIn session already authenticated")
                    return

        raise RuntimeError(
            "LinkedIn session not authenticated. "
            "Run `make sign-in-linkedin` or `scripts/linkedin_sign_in.py` first."
        )


__all__ = [
    "LinkedInFeedAgent",
    "default_export_path",
    "write_feed_export",
]

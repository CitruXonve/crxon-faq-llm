---
name: linkedin-feed-collect
description: >-
  Scrapes the LinkedIn feed for hiring-announcement posts and returns structured
  JSON with company URLs, job listing URLs, author profile URLs, and post URLs.
  Use when the user wants to collect hiring signals from their LinkedIn feed.
  Requires an authenticated LinkedIn session (run linkedin-sign-in first if needed).
disable-model-invocation: true
---

# LinkedIn Feed Collect

**All project skills and CLI commands:** [SKILL.md](../SKILL.md)

Collects hiring-announcement posts from the LinkedIn feed using an in-browser
scroll-and-extract loop. Detection uses job listing link presence plus keyword
matching (hiring, open role, now hiring, …).

## Parameters

| Param | Default | CLI flag | `run --steps` field |
|-------|---------|----------|---------------------|
| `max_posts` | `10` | `--max-posts N` | `"max_posts": N` |
| `scroll_px` | `800` | `--scroll-px N` | `"scroll_px": N` |
| `wait_ms` | `2000` | `--wait-ms N` | `"wait_ms": N` |
| `max_scrolls` | `25` | `--max-scrolls N` | `"max_scrolls": N` |

## Prerequisites

- [ ] `poetry run playwright install chromium`
- [ ] Authenticated LinkedIn session — run **linkedin-sign-in** if `check-auth` returns `"authenticated": false`

## Shell alias

```bash
BM="poetry run python src/utility/browser_manager_cli.py \
  --user-data-dir .browser_profile --profile-directory Default --no-headless"
```

## Step 0 — Authentication gate

```bash
$BM check-auth
```

If unauthenticated, run **linkedin-sign-in**, then recheck before continuing.

## Step 1 — Collect hiring posts

### Standalone command (opens and closes browser)

```bash
$BM hiring-posts --max-posts 10
```

### Inside `run --steps` (shares session with navigate / wait)

```bash
$BM run --steps '[
  {"op": "navigate", "url": "https://www.linkedin.com/feed/"},
  {"op": "wait", "timeout_ms": 4000},
  {"op": "hiring-posts", "max_posts": 10}
]'
```

The `hiring-posts` op runs its own internal scroll loop — no separate `scroll-until`
step is needed. Use `run --steps` when you need to navigate first or chain with
other ops in the same browser session.

## Output schema

`data.posts` is an array; one entry per detected hiring post:

```json
[
  {
    "company_urls": ["https://www.linkedin.com/company/..."],
    "job_listing_urls": ["https://www.linkedin.com/jobs/view/..."],
    "author_profile_url": "https://www.linkedin.com/in/...",
    "post_url": "https://www.linkedin.com/feed/update/..."
  }
]
```

- `company_urls` — all `/company/` links found in the post; `[]` if none
- `job_listing_urls` — all `/jobs/view/` links found; `[]` if none
- `author_profile_url` — first `/in/` link (post author); `null` if not found
- `post_url` — `/feed/update/` or `/posts/…_activity` permalink; `null` for ads

## Step 2 — Save export

```bash
mkdir -p .export
printf '%s' "$JSON" > ".export/linkedin_hiring_$(date +%Y-%m-%dT%H:%M:%S%z).json"
```

## Guardrails

- Never invent URLs — only use values returned from the `hiring-posts` step.
- Standalone `hiring-posts` navigates to the **current page** — navigate first or
  use `run --steps` if you need to land on the feed.
- The internal loop scrolls `window` (not a scrollable container); run in
  `--no-headless` mode so the viewport is real and lazy-loaded cards render.

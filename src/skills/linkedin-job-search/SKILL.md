---
name: linkedin-job-search
description: >-
  Collects LinkedIn feed hiring posts and exports linkedin_posts_*.json using
  BrowserManager CLI steps derived from DEFAULT_LINKEDIN_TASK_TEMPLATE. Use when
  the user wants LinkedIn job-search intelligence, recent feed scrape, or hiring
  post URLs with company and author profiles.
disable-model-invocation: true
---

# LinkedIn job search (Step 0 + steps 1–4)

**All project skills and CLI commands:** [SKILL.md](../SKILL.md)

Parameters (defaults match `LinkedInWebAgent`):

| Param | Default | Where |
|-------|---------|-------|
| `max_posts` | 5 | Step 1–2 `run --steps` (`feed-posts`) |
| `recency_hours` | 48 | Step 3 agent filter |

## Prerequisites

- [ ] `poetry run playwright install chromium`
- [ ] Persistent profile: `--user-data-dir .browser_profile --profile-directory Default --no-headless`
- [ ] User signed in to LinkedIn (Step 0 / `linkedin-sign-in` if needed)

## Browser session rule (CRITICAL)

**Each `$BM <subcommand>` starts a new Chromium process and closes it when the command exits.**

- Cookies persist via `--user-data-dir`, but **the open tab does not carry over** between commands.
- Running `$BM navigate …` then `$BM title` / `$BM js` / `$BM text` in separate invocations leaves the second command on a **fresh blank page** → empty title, null JS, failed sort.
- **Do not** use separate `navigate`, `title`, `text`, or `screenshot` commands to debug Step 1 after navigation.
- **Do** use a single `run --steps '[...]'` for Steps 1–2 (and any extra `js` / `wait` in between).

CLI JSON includes `"session_mode": "ephemeral"` (one-shot commands) or `"multi_step"` (`run`). Empty `title` responses include a `hint` field — follow it.

## Execution modes

| Mode | Command |
|------|---------|
| **Skill-driven** (this skill) | `scripts/browser_manager.py` per steps below |
| **One-shot LangChain** | `poetry run python -m src.utility.browser` |

## Shell alias

```bash
BM="poetry run python scripts/browser_manager.py \
  --user-data-dir .browser_profile --profile-directory Default --no-headless"
```

## Workflow (from DEFAULT_LINKEDIN_TASK_TEMPLATE)

Execute IN ORDER:

### Step 0 — Authentication gate (required)

`check-auth` is a standalone command (OK as its own invocation).

```bash
$BM check-auth
```

If unauthenticated (`"error": "linkedin_not_authenticated"`), stop and run the **`linkedin-sign-in`** skill. After sign-in completes, rerun `$BM check-auth`. Do not continue until `"authenticated": true`.

### Steps 1–2 — Feed, sort, collect (single browser session)

Navigate to the LinkedIn feed, sort by recent, and collect posts in **one** `run --steps` call:

```bash
$BM run --steps "$(python3 - <<'PY'
import json
from pathlib import Path

sort_js = Path("src/skills/linkedin-job-search/examples/linkedin_sort_recent.js").read_text()
print(json.dumps([
    {"op": "navigate", "url": "https://www.linkedin.com/feed/"},
    {"op": "js", "code": sort_js},
    {"op": "wait", "timeout_ms": 2000},
    {"op": "feed-posts", "max_posts": 5, "scroll_rounds": 3},
]))
PY
)"
```

- Adjust `max_posts` / `scroll_rounds` as needed.
- If sort JS returns `{sorted: false}`, add another `{"op":"js","code":"..."}` step in the **same** `run` array (or try `https://www.linkedin.com/feed/?feedType=recent` as the navigate URL) — still within one `run`.
- Parse stdout: `data.steps[-1].data.posts` (last step should be `feed-posts`).

**Forbidden pattern (causes empty title / lost session):**

```bash
# WRONG — each line is a new browser
$BM navigate https://www.linkedin.com/feed/
$BM js --file src/skills/linkedin-job-search/examples/linkedin_sort_recent.js
$BM feed-posts --max-posts 5
```

### Step 3 — Filter hiring announcements

For each raw post that looks like a hiring announcement, record:

- a. The company's LinkedIn URL.
- b. The job listing URL (if present, otherwise null).
- c. The author's profile URL.
- d. The post URL.

Never invent URLs — only use values from Step 2 JSON.

Output schema (one entry per post; `company_urls` and `job_listing_urls` are lists to handle posts that mention multiple companies or roles):

```json
[
  {
    "company_urls": ["https://www.linkedin.com/company/..."],
    "job_listing_urls": ["https://www.linkedin.com/jobs/view/...", null],
    "author_profile_url": "https://www.linkedin.com/in/...",
    "post_url": "https://www.linkedin.com/feed/update/..."
  }
]
```

Use an empty list `[]` when no company or job URL is present.

### Step 4 — Save JSON export

Write `linkedin_posts_<timestamp>.json` under `.export/`:

```bash
mkdir -p .export
printf '%s' "$JSON" > ".export/linkedin_posts_$(date +%Y-%m-%dT%H:%M:%S%z).json"
```

Or use the Cursor Write tool.

## Checklist

```
- [ ] Step 0: check-auth passed
- [ ] Steps 1–2: one run --steps completed (session_mode multi_step)
- [ ] Step 3: hiring entries filtered (≤ recency_hours)
- [ ] Step 4: file written under .export/
```

## Guardrails

- Never paste raw HTML or base64 screenshots into chat.
- Prefer `feed-posts` inside `run --steps`, not a separate `feed-posts` command after `navigate`.
- Browser `js` must use DevTools CSS/XPath only.

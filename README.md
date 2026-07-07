# social-read

`social-read` captures LinkedIn, Reddit, and X post URLs into structured artifacts that
coding agents can read without improvising inside a social feed.

It uses Playwriter to drive a browser session. There is no LinkedIn API path,
no Reddit API path, no X API path, and no alternate Python browser backend.

## What It Produces

```text
capture/
  manifest.json
  post.json
  post.md
  screenshots/
    full-page.png
    post.png
  raw/
    rendered.html       # only with --save-html
```

`post.json` is the source artifact for agents:

```json
{
  "platform": "x",
  "url": "https://x.com/user/status/123",
  "post_id": "123",
  "author": {"name": "User", "handle": "@user", "url": "https://x.com/user"},
  "text": "Post text...",
  "comments": [],
  "screenshots": ["screenshots/full-page.png", "screenshots/post.png"],
  "warnings": []
}
```

## Install

From this checkout:

```sh
uv tool install --force .
```

Or run without installing:

```sh
uv run social-read doctor
```

Install Playwriter if needed:

```sh
npm install -g playwriter@latest
```

## Quick Start

Capture a post:

```sh
social-read "https://x.com/user/status/123" --out ./captures/post
```

Capture a public Reddit post:

```sh
social-read "https://www.reddit.com/r/FacebookAds/comments/1t0te6o/example/" \
  --out ./captures/reddit-post \
  --comments
```

Capture comments and replies too:

```sh
social-read "https://www.linkedin.com/feed/update/urn:li:activity:123/" \
  --out ./captures/linkedin-post \
  --comments
```

Print the run manifest:

```sh
social-read "https://x.com/user/status/123" --out ./captures/post --json
```

## Playwriter Sessions

By default, `social-read` creates a temporary Playwriter session and lets
Playwriter choose the browser path. In a normal local setup, that means the
tool can use the Chrome instance exposed through Playwriter.

Reuse an existing Playwriter session:

```sh
playwriter session list
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --session 42
```

Keep an auto-created session for later inspection:

```sh
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --keep-session
```

Create a headless Playwriter session:

```sh
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --headless
```

If Playwriter reports that no Chrome browser was found for headless mode, run:

```sh
playwriter browser install
```

Use Playwriter direct-CDP mode:

```sh
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --direct localhost:9222
```

## Comments

`--comments` repeatedly clicks visible expansion controls and scrolls until the
page stops yielding new comment/reply nodes. For Reddit, the tool captures the
public old.reddit.com rendering and clicks native `load more comments` controls
(`.thing[data-type="morechildren"] .morecomments > a.button`) before extraction.

Useful bounds:

```sh
social-read URL --out ./captures/post --comments --max-expansion-rounds 50
social-read URL --out ./captures/post --comments --max-comments 200
```

Follow platform redirects during comment expansion:

```sh
social-read URL \
  --out ./captures/post \
  --comments \
  --follow-comment-redirects
```

Use recursive comment URL traversal only when the captured platform page still
has unresolved branches or when you need a deeper verification pass. It visits
captured comment permalinks and attaches their replies under the parent comment:

```sh
social-read URL \
  --out ./captures/post \
  --comment-tree
```

Bound the recursive traversal when needed:

```sh
social-read URL \
  --out ./captures/post \
  --comment-tree \
  --max-comment-depth 2 \
  --max-comment-visits 25 \
  --max-comments 200
```

The expansion loop is intentionally UI-driven because LinkedIn and X do not
expose the full rendered discussion as static HTML. If the platform withholds
some replies behind permissions, login walls, deleted content, or collapsed
branches the tool cannot open, the run finishes with warnings and partial
artifacts.

## Commands

| Command | Purpose |
| --- | --- |
| `social-read doctor` | Check Playwriter availability |
| `social-read capture URL --out DIR` | Capture one LinkedIn, Reddit, or X post |
| `social-read URL --out DIR` | Shorthand for `capture` |

## Development

```sh
uv run --extra dev pytest
uv run ruff check .
```

Important options:

| Option | Purpose |
| --- | --- |
| `--comments` | Expand and capture comments/replies |
| `--follow-comment-redirects` | Continue from platform redirects during comment expansion |
| `--comment-tree` | Recursively visit captured comment URLs for nested replies |
| `--max-comment-depth N` | Cap recursive reply traversal depth |
| `--max-comment-visits N` | Cap comment pages visited during recursive traversal |
| `--max-comments N` | Cap extracted comments after expansion |
| `--max-expansion-rounds N` | Cap comment expansion loop |
| `--session ID` | Reuse an existing Playwriter session |
| `--headless` | Create a Playwriter headless session |
| `--browser headless|cloud` | Pick the browser key for a new Playwriter session |
| `--direct [ENDPOINT]` | Create a direct-CDP Playwriter session |
| `--keep-session` | Keep an auto-created Playwriter session |
| `--save-html` | Save `raw/rendered.html` for debugging |

## Agent Workflow

1. Run `social-read doctor`.
2. Run `social-read URL --out DIR`.
3. Add `--comments` when the task needs the discussion, not just the post.
4. Read `post.json` first, then `post.md`, then screenshots if visual context matters.
5. Treat `warnings` as part of the source record.

For Reddit URLs, `social-read` captures the public old.reddit.com rendering of
the requested post URL when possible. This keeps capture browser-only while
avoiding Reddit's unauthenticated verification page on the default web host.

## Privacy

The tool saves rendered social content to disk. When using a logged-in browser
profile, captured pages may include private or personalized content. Keep output
folders out of public repos unless you have reviewed them.

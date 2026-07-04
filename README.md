# social-read

`social-read` captures LinkedIn and X post URLs into structured artifacts that
coding agents can read without improvising inside a social feed.

It uses Playwright only. There is no LinkedIn API path and no X API path.

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

Install Playwright's bundled Chromium if needed:

```sh
uv run playwright install chromium
```

## Quick Start

Capture a post:

```sh
social-read "https://x.com/user/status/123" --out ./captures/post
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

## Browser Sessions

By default, `social-read` opens headed Chrome with a persistent profile at:

```text
~/.local/share/social-read/chrome-profile
```

Log into LinkedIn or X once in that profile, then later captures can reuse the
session.

Use bundled Chromium instead of local Chrome:

```sh
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --browser-channel chromium
```

Attach to an existing Chromium debugging endpoint:

```sh
social-read "https://x.com/user/status/123" \
  --out ./captures/post \
  --cdp-url http://127.0.0.1:9222
```

## Comments

`--comments` repeatedly clicks visible expansion controls and scrolls until the
page stops yielding new comment/reply nodes.

Useful bounds:

```sh
social-read URL --out ./captures/post --comments --max-expansion-rounds 50
social-read URL --out ./captures/post --comments --max-comments 200
```

The expansion loop is intentionally UI-driven because LinkedIn and X do not
expose the full rendered discussion as static HTML. If the platform withholds
some replies behind permissions, login walls, deleted content, or collapsed
branches the tool cannot open, the run finishes with warnings and partial
artifacts.

## Commands

| Command | Purpose |
| --- | --- |
| `social-read doctor` | Check Playwright and browser launch |
| `social-read capture URL --out DIR` | Capture one LinkedIn or X post |
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
| `--max-comments N` | Cap extracted comments after expansion |
| `--max-expansion-rounds N` | Cap comment expansion loop |
| `--headless` | Run without a visible browser |
| `--profile-dir DIR` | Use a specific persistent Chrome profile |
| `--browser-channel chrome|chromium` | Choose local Chrome or bundled Chromium |
| `--save-html` | Save `raw/rendered.html` for debugging |

## Agent Workflow

1. Run `social-read doctor`.
2. Run `social-read URL --out DIR`.
3. Add `--comments` when the task needs the discussion, not just the post.
4. Read `post.json` first, then `post.md`, then screenshots if visual context matters.
5. Treat `warnings` as part of the source record.

## Privacy

The tool saves rendered social content to disk. When using a logged-in browser
profile, captured pages may include private or personalized content. Keep output
folders out of public repos unless you have reviewed them.

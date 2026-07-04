# AGENTS.md

Act like a senior engineer working on a small public CLI.

- Keep the browser path Playwriter-only. Do not add alternate Python browser, LinkedIn API, or X API paths.
- Preserve source-faithful extraction. Use declared platform DOM selectors and return warnings when expected fields are missing.
- Do not guess post text from page titles, broad page text, or unrelated feed content.
- Keep output artifacts stable: `manifest.json`, `post.json`, `post.md`, and `screenshots/`.
- Run `uv run --extra dev pytest` and `uv run ruff check .` before shipping code changes.

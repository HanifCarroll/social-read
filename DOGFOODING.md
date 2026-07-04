# Dogfooding Notes

This file records CLI dogfooding rounds and the UX changes made after each run.

## Round Log

### Round 1: Environment Check

- Command: `uv run social-read doctor --json`
- Result: passed. Playwright import and bundled Chromium launch worked.
- UX note: `pytest` needed `--extra dev` because dev dependencies are optional.
- Change made: keep package dependencies lean; update docs/agent instructions to use the dev extra.

### Round 2: X Basic Capture, First Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood/x-basic --browser-channel chromium --headless --json`
- Result: artifacts were written, but `post.md` had no post text and warned that no tweet article matched.
- UX note: a run with a visible post screenshot but empty structured content is not useful enough.
- Change made: X extraction now supports current public X markup with `article[data-tweet-id]` and OpenGraph metadata for primary post text/author.

### Round 3: X Basic Capture, Second Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood/x-basic-2 --browser-channel chromium --headless --json`
- Result: passed. `post.json`, `post.md`, and `screenshots/post.png` captured author, text, timestamp, URL, and visual context.
- UX note: the basic capture output is readable and agent-usable.
- Change made: none.

### Round 4: X Comments Capture, First Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood/x-comments --browser-channel chromium --headless --comments --max-expansion-rounds 8 --json`
- Result: completed with `comment_count: 0` and no warning, even though the page showed `Read 439 replies`.
- UX note: comments mode needs to click X's `Read N replies` control and must warn when comments were requested but none were captured.
- Change made: added the `Read N replies` expansion pattern and a zero-comments warning.

### Round 5: X Comments Capture, Second Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood/x-comments-2 --browser-channel chromium --headless --comments --max-expansion-rounds 8 --json`
- Result: completed with a zero-comments warning. Screenshot showed that X opened a login modal: `Join X now to read replies on this post.`
- UX note: this is a platform/login blocker, not just an empty comment result. Screenshots should not remain obscured by the modal.
- Change made: added X reply-login blocker detection and modal closing before screenshots.

### Round 6: X Comments Capture, Third Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood/x-comments-3 --browser-channel chromium --headless --comments --max-expansion-rounds 8 --json`
- Result: completed with explicit `X blocked reply capture behind a login modal.` warning and readable screenshots.
- UX note: logged-out X cannot read replies from this page, but the blocker is now represented as source context instead of silent absence.
- Change made: none.

### Round 7: LinkedIn Basic Capture, First Pass

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood/linkedin-basic --browser-channel chromium --headless --json`
- Result: captured post text, but author name was missing, media included unrelated avatars/static assets, and screenshots were obscured by a sign-in modal.
- UX note: public LinkedIn exposes better structured data than the visible DOM through `application/ld+json`.
- Change made: LinkedIn extraction now prefers `SocialMediaPosting` JSON-LD for author, date, body, image, and public comments; screenshots now target `article.main-feed-activity-card`.

### Round 8: LinkedIn Basic Capture, Second Pass

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood/linkedin-basic-2 --browser-channel chromium --headless --json`
- Result: author, timestamp, body, media, and screenshots were clean. LinkedIn's automatic sign-in modal was detected and closed.
- UX note: basic capture should not click comment controls, because that creates unnecessary login prompts.
- Change made: split post-text expansion controls from comment-expansion controls.

### Round 9: LinkedIn Comments Capture

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood/linkedin-comments --browser-channel chromium --headless --comments --max-expansion-rounds 8 --json`
- Result: captured all 8 public JSON-LD comments with no warnings.
- UX note: logged-in runs may load comments beyond the initial schema.
- Change made: merge schema comments with any loaded DOM comments and warn if LinkedIn declares more comments than captured.

### Round 10: LinkedIn Comments Capture, Merge Check

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood/linkedin-comments-2 --browser-channel chromium --headless --comments --max-expansion-rounds 8 --json`
- Result: still captured 8 comments with no warnings after the merge change.
- UX note: output is stable for the public LinkedIn case.
- Change made: none.

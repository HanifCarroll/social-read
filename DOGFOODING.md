# Dogfooding Notes

This file records CLI dogfooding rounds and UX changes made after each run.

## Round Log

### Round 1: Playwriter Doctor

- Command: `uv run social-read doctor --json`
- Result: passed with `/Users/hanifcarroll/.bun/bin/playwriter`.
- UX note: doctor should report Playwriter version, session-list health, and active session count.
- Change made: doctor now reports Playwriter-specific environment fields.

### Round 2: Headless Session

- Command: `uv run social-read "https://x.com/OpenAI/status/1932443370452037804" --out /tmp/social-read-dogfood-playwriter/x-basic --headless --json`
- Result: failed because Playwriter headless Chrome was not installed.
- UX note: the error was actionable, but the README should mention the prerequisite.
- Change made: README now documents `playwriter browser install` for `--headless`.

### Round 3: X Basic Capture, First Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-basic-2 --json`
- Result: X redirected inside the logged-in browser before extraction, so no tweet article was captured.
- UX note: final-URL drift should be explicit source context.
- Change made: the manifest/post warnings now report when X redirects away from the requested status URL.

### Round 4: X Basic Capture, Second Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-basic-3 --json`
- Result: passed. Captured author, post text, timestamp, post id, full-page screenshot, and post screenshot.
- UX note: auto-created Playwriter sessions should not accumulate.
- Change made: verified auto-created sessions are deleted after successful runs unless `--keep-session` is passed.

### Round 5: X Comments Capture, First Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-comments --comments --max-expansion-rounds 8 --json`
- Result: comment expansion redirected away from the requested status and lost the primary post.
- UX note: comments mode must preserve the base post even when expansion drifts.
- Change made: the Playwriter script now extracts the base post before expanding comments and restores the requested URL for screenshots when expansion redirects away.

### Round 6: X Comments Capture, Second Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-comments-2 --comments --max-expansion-rounds 8 --json`
- Result: passed with the primary post, screenshots, and 19 captured replies. The warning explains that X redirected during further expansion.
- UX note: this is a useful partial artifact because the limitation is explicit.
- Change made: none.

### Round 7: LinkedIn Basic Capture, First Pass

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood-playwriter/linkedin-basic --json`
- Result: captured the post, but logged-in LinkedIn DOM produced noisy author and timestamp strings.
- UX note: logged-in LinkedIn has cleaner actor fields than the broad actor container text.
- Change made: LinkedIn extraction now prefers exact actor/timestamp selectors from the rendered DOM.

### Round 8: LinkedIn Basic Capture, Second Pass

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood-playwriter/linkedin-basic-2 --json`
- Result: passed with clean author, timestamp, post text, and screenshots.
- UX note: structured artifacts are now readable without manual cleanup.
- Change made: none.

### Round 9: LinkedIn Comments Capture

- Command: `uv run social-read "https://www.linkedin.com/posts/andresnds_github-openaigpt-oss-gpt-oss-120b-and-activity-7358548194995109888-wWMl" --out /tmp/social-read-dogfood-playwriter/linkedin-comments-2 --comments --max-expansion-rounds 8 --json`
- Result: passed with 8 comments, clean author, screenshots, and no warnings.
- UX note: comment capture stayed stable after the LinkedIn selector fix.
- Change made: none.

### Round 10: Session Cleanup Check

- Command: `playwriter session list`
- Result: no new `social-read` sessions remained after dogfooding.
- UX note: default cleanup works; `--keep-session` remains available for debugging.
- Change made: none.

### Round 11: X Comments With Redirect Following

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-follow-redirects --comments --follow-comment-redirects --max-expansion-rounds 8 --json`
- Result: followed X's redirected route during comment expansion and recorded it in `comment_capture.redirects_followed`.
- UX note: redirect following needs explicit metadata so downstream agents can see that the capture left the requested post URL.
- Change made: manifest now includes `comments_complete` and a `comment_capture` object with mode, redirect policy, redirects followed, visited comment URLs, and stop reason.

### Round 12: X Comment Tree, First Pass

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-comment-tree-depth1-2 --comment-tree --max-comment-depth 1 --max-comments 15 --max-expansion-rounds 8 --json`
- Result: traversal ran too long for practical dogfooding and was interrupted.
- UX note: `--max-comments` does not bound page visits early enough during recursive traversal.
- Change made: added `--max-comment-visits` to cap the number of comment URLs visited by `--comment-tree`.

### Round 13: X Comment Tree With Visit Cap

- Command: `uv run social-read "https://x.com/OpenAI/status/2062927046448431587" --out /tmp/social-read-dogfood-playwriter/x-comment-tree-visit1 --comment-tree --max-comment-depth 1 --max-comment-visits 1 --max-comments 25 --max-expansion-rounds 2 --playwriter-timeout-ms 180000 --json`
- Result: visited one comment URL, kept the base post, wrote full-page and post screenshots, and recorded `visited_comment_urls`.
- UX note: the sampled visited comment had no nested replies, but the traversal path and metadata are working.
- Change made: added an X screenshot fallback that uses the first tweet article when the exact post selector is unavailable after traversal.

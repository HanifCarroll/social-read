from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error,
    Page,
    TimeoutError,
    async_playwright,
)

from .extractors import extract_post
from .markdown import render_markdown
from .models import CaptureConfig, CapturePaths, SocialPost, to_plain
from .urls import default_post_id, detect_platform

X_TEXT_EXPAND_BUTTONS = [
    re.compile(r"^(show more|show this thread)$", re.I),
]

X_COMMENT_EXPAND_BUTTONS = [
    re.compile(r"^(show more|show this thread|show replies|show more replies)$", re.I),
    re.compile(r"^(show additional replies|view replies|view more replies)$", re.I),
    re.compile(r"^read [\d,.km]+ replies$", re.I),
]

LINKEDIN_TEXT_EXPAND_BUTTONS = [
    re.compile(r"^(see more)$", re.I),
]

LINKEDIN_COMMENT_EXPAND_BUTTONS = [
    re.compile(r"^(see more)$", re.I),
    re.compile(r"^(load more comments|show more comments|view previous comments)$", re.I),
    re.compile(r"^(show previous comments|view replies|show replies|load more replies).*$", re.I),
]


async def capture(config: CaptureConfig) -> dict[str, Any]:
    platform = detect_platform(config.url)
    paths = prepare_paths(config.output_dir)
    started_at = datetime.now(UTC).isoformat()

    async with async_playwright() as playwright:
        context, browser, should_close_context = await _open_context(playwright, config)
        page = await context.new_page()
        page.set_default_timeout(config.timeout_ms)
        warnings: list[str] = []
        try:
            response = await page.goto(
                config.url,
                wait_until="domcontentloaded",
                timeout=config.timeout_ms,
            )
            if response is not None and response.status >= 400:
                warnings.append(f"Initial navigation returned HTTP {response.status}.")
            await page.wait_for_timeout(config.wait_ms)

            await _expand_post_text(page, platform=platform, wait_ms=config.wait_ms)
            await _detect_sign_in_blockers(page, platform=platform, warnings=warnings)
            if config.include_comments:
                await _expand_comments(
                    page,
                    platform=platform,
                    max_rounds=config.max_expansion_rounds,
                    wait_ms=config.wait_ms,
                    warnings=warnings,
                )
                await _detect_sign_in_blockers(page, platform=platform, warnings=warnings)

            post = await extract_post(
                page,
                platform=platform,
                requested_url=config.url,
                include_comments=config.include_comments,
                max_comments=config.max_comments,
            )
            post.warnings.extend(warnings)
            if config.include_comments and _count_comments(post) == 0:
                post.warnings.append(
                    "Comments were requested, but no comments were captured. "
                    "The page may require login, or no replies were loaded."
                )

            await _write_screenshots(page, post, paths, config.url)
            if config.save_html:
                (paths.raw_dir / "rendered.html").write_text(await page.content(), encoding="utf-8")

            _write_post_files(post, paths)
            manifest = _build_manifest(config, post, paths, started_at)
            paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            return manifest
        finally:
            await _close_page(page)
            await _close_browser(context, browser, should_close_context)


def prepare_paths(output_dir: Path) -> CapturePaths:
    screenshot_dir = output_dir / "screenshots"
    raw_dir = output_dir / "raw"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    return CapturePaths(
        output_dir=output_dir,
        manifest=output_dir / "manifest.json",
        post_json=output_dir / "post.json",
        post_md=output_dir / "post.md",
        screenshot_dir=screenshot_dir,
        raw_dir=raw_dir,
    )


async def _open_context(
    playwright: Any,
    config: CaptureConfig,
) -> tuple[BrowserContext, Browser | None, bool]:
    viewport = {"width": config.viewport_width, "height": config.viewport_height}
    if config.cdp_url:
        browser = await playwright.chromium.connect_over_cdp(
            config.cdp_url,
            timeout=config.timeout_ms,
        )
        if browser.contexts:
            return browser.contexts[0], browser, False
        context = await browser.new_context(viewport=viewport)
        return context, browser, True

    profile_dir = config.profile_dir or Path.home() / ".local/share/social-read/chrome-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    channel = None if config.browser_channel == "chromium" else config.browser_channel
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel=channel,
        headless=config.headless,
        viewport=viewport,
    )
    return context, None, True


async def _expand_post_text(page: Page, *, platform: str, wait_ms: int) -> None:
    patterns = X_TEXT_EXPAND_BUTTONS if platform == "x" else LINKEDIN_TEXT_EXPAND_BUTTONS
    for _ in range(3):
        clicked = await _click_matching_buttons(page, patterns, max_clicks=8)
        if clicked == 0:
            return
        await page.wait_for_timeout(min(wait_ms, 1000))


async def _expand_comments(
    page: Page,
    *,
    platform: str,
    max_rounds: int,
    wait_ms: int,
    warnings: list[str],
) -> None:
    patterns = X_COMMENT_EXPAND_BUTTONS if platform == "x" else LINKEDIN_COMMENT_EXPAND_BUTTONS
    previous_signature: dict[str, Any] | None = None
    stable_rounds = 0

    for _ in range(max_rounds):
        clicked = await _click_matching_buttons(page, patterns, max_clicks=20)
        await page.mouse.wheel(0, 3000)
        await page.wait_for_timeout(wait_ms)
        signature = await _page_signature(page, platform=platform)

        if signature == previous_signature and clicked == 0:
            stable_rounds += 1
        else:
            stable_rounds = 0

        previous_signature = signature
        if stable_rounds >= 3:
            break
    else:
        warnings.append(f"Stopped comment expansion after {max_rounds} rounds.")

    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(min(wait_ms, 1000))


async def _detect_sign_in_blockers(page: Page, *, platform: str, warnings: list[str]) -> None:
    if platform == "x":
        blocker = page.get_by_text("Join X now to read replies on this post")
        warning = "X blocked reply capture behind a login modal."
    else:
        blocker = page.get_by_text("Sign in to view more content")
        warning = "LinkedIn opened a sign-in modal."

    try:
        if await blocker.count() == 0:
            return
        if not await blocker.first.is_visible(timeout=500):
            return
    except (Error, TimeoutError):
        return

    warnings.append(warning)
    close_button = page.get_by_role("button", name=re.compile(r"^(close|x|dismiss)$", re.I))
    try:
        if await close_button.count() > 0:
            await close_button.first.click(timeout=1200)
        else:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
    except (Error, TimeoutError):
        warnings.append(f"Could not close the {platform} sign-in modal before screenshots.")


async def _click_matching_buttons(
    page: Page,
    patterns: list[re.Pattern[str]],
    *,
    max_clicks: int,
) -> int:
    clicks = 0
    for pattern in patterns:
        if clicks >= max_clicks:
            break
        locator = page.get_by_role("button", name=pattern)
        try:
            count = await locator.count()
        except Error:
            continue
        for index in range(count):
            if clicks >= max_clicks:
                break
            button = locator.nth(index)
            try:
                if not await button.is_visible(timeout=500):
                    continue
                if not await button.is_enabled(timeout=500):
                    continue
                await button.click(timeout=1200)
                clicks += 1
                await page.wait_for_timeout(250)
            except (Error, TimeoutError):
                continue
    return clicks


async def _page_signature(page: Page, *, platform: str) -> dict[str, Any]:
    return await page.evaluate(
        """
        (platform) => {
          const tweetCount = document.querySelectorAll(
            'article[data-tweet-id], article[data-testid="tweet"], article'
          ).length;
          const commentCount = document.querySelectorAll(
            ".comments-comment-item, .comments-comment-entity, [data-test-id='comment']"
          ).length;
          return {
            platform,
            tweetCount,
            commentCount,
            height: document.documentElement ? document.documentElement.scrollHeight : 0,
            y: window.scrollY,
          };
        }
        """,
        platform,
    )


async def _write_screenshots(page: Page, post: SocialPost, paths: CapturePaths, url: str) -> None:
    full_page = paths.screenshot_dir / "full-page.png"
    await page.screenshot(path=str(full_page), full_page=True)
    post.screenshots.append(str(full_page.relative_to(paths.output_dir)))

    post_screenshot = paths.screenshot_dir / "post.png"
    locator = _primary_post_locator(page, post.platform, url)
    if locator is None:
        post.warnings.append("Primary post screenshot locator was not available.")
        return
    try:
        if await locator.count() == 0:
            post.warnings.append("Primary post screenshot target was not found.")
            return
        await locator.first.screenshot(path=str(post_screenshot))
        post.screenshots.append(str(post_screenshot.relative_to(paths.output_dir)))
    except (Error, TimeoutError) as exc:
        post.warnings.append(f"Primary post screenshot failed: {exc.__class__.__name__}.")


def _primary_post_locator(page: Page, platform: str, url: str) -> Any:
    post_id = default_post_id(platform, url)
    if platform == "x":
        if post_id:
            return page.locator(
                f'article[data-tweet-id="{post_id}"], a[href*="/status/{post_id}"]'
            ).first.locator(
                "xpath=ancestor-or-self::article[1]"
            )
        return page.locator('article[data-tweet-id], article[data-testid="tweet"], article')

    if post_id and post_id.startswith("urn:li:"):
        return page.locator(
            f'article[data-activity-urn="{post_id}"], '
            f'article[data-featured-activity-urn="{post_id}"], '
            f'[data-urn="{post_id}"], [data-id="{post_id}"]'
        )
    return page.locator("article.main-feed-activity-card, .feed-shared-update-v2, main")


def _write_post_files(post: SocialPost, paths: CapturePaths) -> None:
    paths.post_json.write_text(json.dumps(to_plain(post), indent=2) + "\n", encoding="utf-8")
    paths.post_md.write_text(render_markdown(post), encoding="utf-8")


def _build_manifest(
    config: CaptureConfig,
    post: SocialPost,
    paths: CapturePaths,
    started_at: str,
) -> dict[str, Any]:
    completed_at = datetime.now(UTC).isoformat()
    return {
        "ok": True,
        "tool": "social-read",
        "started_at": started_at,
        "completed_at": completed_at,
        "platform": post.platform,
        "url": config.url,
        "final_url": post.final_url,
        "comments_requested": config.include_comments,
        "comment_count": _count_comments(post),
        "output_dir": str(paths.output_dir),
        "files": {
            "post_json": str(paths.post_json.relative_to(paths.output_dir)),
            "post_md": str(paths.post_md.relative_to(paths.output_dir)),
            "manifest": str(paths.manifest.relative_to(paths.output_dir)),
            "screenshots": post.screenshots,
        },
        "warnings": post.warnings,
    }


def _count_comments(post: SocialPost) -> int:
    def count(items: list[Any]) -> int:
        return sum(1 + count(item.replies) for item in items)

    return count(post.comments)


async def _close_page(page: Page) -> None:
    with suppress(Error):
        await page.close()


async def _close_browser(
    context: BrowserContext,
    browser: Browser | None,
    should_close_context: bool,
) -> None:
    if should_close_context:
        with suppress(Error):
            await context.close()
    if browser is not None:
        disconnect = getattr(browser, "disconnect", None)
        if disconnect is not None:
            await disconnect()

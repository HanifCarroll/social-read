from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from playwright.async_api import Error, async_playwright

from . import __version__
from .browser import capture
from .models import CaptureConfig
from .urls import UnsupportedUrlError, detect_platform


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].startswith(("http://", "https://")):
        argv.insert(0, "capture")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return asyncio.run(_doctor(json_output=args.json))
    if args.command == "capture":
        return asyncio.run(_capture(args))

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="social-read",
        description="Capture LinkedIn and X posts into structured artifacts with Playwright.",
    )
    parser.add_argument("--version", action="version", version=f"social-read {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="Check Playwright import and browser launch.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable output.")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture one LinkedIn or X post URL.",
    )
    capture_parser.add_argument("url", help="LinkedIn or X post URL.")
    capture_parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory for manifest.json, post.json, post.md, and screenshots.",
    )
    capture_parser.add_argument(
        "--comments",
        action="store_true",
        help="Expand and capture visible comments/replies before extraction.",
    )
    capture_parser.add_argument(
        "--max-comments",
        type=int,
        default=None,
        help="Optional cap on extracted comments after expansion.",
    )
    capture_parser.add_argument(
        "--max-expansion-rounds",
        type=int,
        default=200,
        help="Maximum expansion/scroll rounds when --comments is enabled.",
    )
    capture_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser headless. Headed mode is the default for login/session visibility.",
    )
    capture_parser.add_argument(
        "--browser-channel",
        default="chrome",
        help=(
            "Playwright browser channel. Use 'chrome' for local Chrome or "
            "'chromium' for bundled Chromium."
        ),
    )
    capture_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help=(
            "Persistent browser profile directory. Defaults to "
            "~/.local/share/social-read/chrome-profile."
        ),
    )
    capture_parser.add_argument(
        "--cdp-url",
        default=None,
        help="Attach to an existing Chromium debugging endpoint, e.g. http://127.0.0.1:9222.",
    )
    capture_parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45_000,
        help="Navigation and operation timeout in milliseconds.",
    )
    capture_parser.add_argument(
        "--wait-ms",
        type=int,
        default=1_500,
        help="Wait between expansion actions in milliseconds.",
    )
    capture_parser.add_argument(
        "--viewport",
        default="1440x1400",
        help="Viewport size as WIDTHxHEIGHT.",
    )
    capture_parser.add_argument(
        "--save-html",
        action="store_true",
        help="Also save raw/rendered.html. This may include private page content.",
    )
    capture_parser.add_argument("--json", action="store_true", help="Print manifest JSON.")
    return parser


async def _capture(args: argparse.Namespace) -> int:
    try:
        platform = detect_platform(args.url)
    except UnsupportedUrlError as exc:
        print(f"social-read: {exc}", file=sys.stderr)
        return 2

    width, height = _parse_viewport(args.viewport)
    config = CaptureConfig(
        url=args.url,
        output_dir=args.out.expanduser(),
        include_comments=args.comments,
        max_comments=args.max_comments,
        max_expansion_rounds=args.max_expansion_rounds,
        headless=args.headless,
        browser_channel=args.browser_channel,
        profile_dir=args.profile_dir.expanduser() if args.profile_dir else None,
        cdp_url=args.cdp_url,
        timeout_ms=args.timeout_ms,
        wait_ms=args.wait_ms,
        viewport_width=width,
        viewport_height=height,
        save_html=args.save_html,
    )

    try:
        manifest = await capture(config)
    except Error as exc:
        print(f"social-read: Playwright error while capturing {platform}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"social-read: file error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        print(
            f"Captured {manifest['platform']} post: "
            f"{manifest['comment_count']} comments, output={manifest['output_dir']}"
        )
        if manifest["warnings"]:
            print("Warnings:")
            for warning in manifest["warnings"]:
                print(f"- {warning}")
    return 0


async def _doctor(*, json_output: bool) -> int:
    result = {
        "ok": True,
        "tool": "social-read",
        "version": __version__,
        "playwright_import": True,
        "chromium_launch": None,
        "warnings": [],
    }
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            result["chromium_launch"] = True
            await browser.close()
    except Exception as exc:  # noqa: BLE001 - doctor should report environment failures.
        result["ok"] = False
        result["chromium_launch"] = False
        result["warnings"].append(str(exc))

    if json_output:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print("social-read doctor: ok")
    else:
        print("social-read doctor: failed")
        for warning in result["warnings"]:
            print(f"- {warning}")
    return 0 if result["ok"] else 1


def _parse_viewport(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("viewport must be WIDTHxHEIGHT") from exc

    if width < 320 or height < 320:
        raise argparse.ArgumentTypeError("viewport dimensions must be at least 320")
    return width, height

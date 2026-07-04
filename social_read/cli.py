from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .browser import PlaywriterError, capture, doctor
from .models import CaptureConfig
from .urls import UnsupportedUrlError, detect_platform


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].startswith(("http://", "https://")):
        argv.insert(0, "capture")

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _doctor(json_output=args.json, playwriter_command=args.playwriter_command)
    if args.command == "capture":
        return _capture(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="social-read",
        description="Capture LinkedIn and X posts into structured artifacts with Playwriter.",
    )
    parser.add_argument("--version", action="version", version=f"social-read {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Check Playwriter availability.")
    doctor_parser.add_argument(
        "--playwriter-command",
        default="playwriter",
        help="Playwriter executable to use.",
    )
    doctor_parser.add_argument("--json", action="store_true", help="Print machine-readable output.")

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
        "--follow-comment-redirects",
        action="store_true",
        help=(
            "When comment expansion navigates away from the requested post, "
            "continue from the redirected page and merge captured comments."
        ),
    )
    capture_parser.add_argument(
        "--comment-tree",
        action="store_true",
        help=(
            "Visit captured comment URLs recursively to capture nested replies. "
            "Implies --comments and --follow-comment-redirects."
        ),
    )
    capture_parser.add_argument(
        "--max-comment-depth",
        type=int,
        default=None,
        help="Optional recursion depth cap for --comment-tree. Omit for no depth cap.",
    )
    capture_parser.add_argument(
        "--max-comment-visits",
        type=int,
        default=None,
        help="Optional cap on comment pages visited by --comment-tree.",
    )
    capture_parser.add_argument(
        "--headless",
        action="store_true",
        help="Create a new Playwriter headless session. Equivalent to --browser headless.",
    )
    capture_parser.add_argument(
        "--session",
        default="auto",
        help="Existing Playwriter session ID to reuse, or 'auto' to create one for this run.",
    )
    capture_parser.add_argument(
        "--browser",
        choices=["headless", "cloud"],
        default=None,
        help=(
            "Browser key for a newly created Playwriter session. "
            "Omit to use Playwriter's default Chrome path."
        ),
    )
    capture_parser.add_argument(
        "--direct",
        nargs="?",
        const="1",
        default=None,
        help=(
            "Create a direct-CDP Playwriter session. "
            "Optionally pass a ws://, wss://, or host:port endpoint."
        ),
    )
    capture_parser.add_argument(
        "--patchright",
        action="store_true",
        help="Pass --patchright when creating a new Playwriter session.",
    )
    capture_parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy region for a newly created Playwriter cloud session, such as 'us'.",
    )
    capture_parser.add_argument(
        "--playwriter-command",
        default="playwriter",
        help="Playwriter executable to use.",
    )
    capture_parser.add_argument(
        "--playwriter-timeout-ms",
        type=int,
        default=600_000,
        help="Maximum Playwriter script execution time in milliseconds.",
    )
    capture_parser.add_argument(
        "--keep-session",
        action="store_true",
        help="Keep an auto-created Playwriter session after capture.",
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


def _capture(args: argparse.Namespace) -> int:
    try:
        platform = detect_platform(args.url)
    except UnsupportedUrlError as exc:
        print(f"social-read: {exc}", file=sys.stderr)
        return 2

    width, height = _parse_viewport(args.viewport)
    config = CaptureConfig(
        url=args.url,
        output_dir=args.out.expanduser(),
        include_comments=args.comments or args.comment_tree,
        max_comments=args.max_comments,
        max_expansion_rounds=args.max_expansion_rounds,
        follow_comment_redirects=args.follow_comment_redirects or args.comment_tree,
        comment_tree=args.comment_tree,
        max_comment_depth=args.max_comment_depth,
        max_comment_visits=args.max_comment_visits,
        playwriter_command=args.playwriter_command,
        playwriter_session=args.session,
        playwriter_browser="headless" if args.headless else args.browser,
        playwriter_direct=args.direct,
        playwriter_patchright=args.patchright,
        playwriter_proxy=args.proxy,
        playwriter_timeout_ms=args.playwriter_timeout_ms,
        keep_session=args.keep_session,
        timeout_ms=args.timeout_ms,
        wait_ms=args.wait_ms,
        viewport_width=width,
        viewport_height=height,
        save_html=args.save_html,
    )

    try:
        manifest = capture(config)
    except PlaywriterError as exc:
        print(f"social-read: Playwriter error while capturing {platform}: {exc}", file=sys.stderr)
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


def _doctor(*, json_output: bool, playwriter_command: str) -> int:
    result = doctor(playwriter_command)
    playwriter_version = result.pop("version", "")
    result["version"] = __version__
    result["playwriter_version"] = playwriter_version

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

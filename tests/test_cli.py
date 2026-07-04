import argparse

import pytest

from social_read.cli import _parse_viewport, build_parser


def test_parser_accepts_capture_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["capture", "https://x.com/u/status/1", "--out", "out"])

    assert args.command == "capture"
    assert args.url == "https://x.com/u/status/1"
    assert str(args.out) == "out"


def test_parser_accepts_playwriter_session_options() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "capture",
            "https://x.com/u/status/1",
            "--out",
            "out",
            "--session",
            "42",
            "--direct",
            "localhost:9222",
            "--keep-session",
        ]
    )

    assert args.session == "42"
    assert args.direct == "localhost:9222"
    assert args.keep_session is True


def test_parser_accepts_direct_without_endpoint() -> None:
    parser = build_parser()
    args = parser.parse_args(["capture", "https://x.com/u/status/1", "--out", "out", "--direct"])

    assert args.direct == "1"


def test_parse_viewport() -> None:
    assert _parse_viewport("1440x900") == (1440, 900)


def test_parse_viewport_rejects_bad_shape() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_viewport("wide")


def test_parse_viewport_rejects_tiny_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_viewport("100x100")

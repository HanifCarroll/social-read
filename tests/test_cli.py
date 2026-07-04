import argparse

import pytest

import social_read.cli as cli
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


def test_comment_tree_implies_comments_and_redirect_following(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_capture(config):
        captured["config"] = config
        return {
            "platform": "x",
            "comment_count": 0,
            "output_dir": str(tmp_path),
            "warnings": [],
        }

    monkeypatch.setattr(cli, "capture", fake_capture)
    parser = build_parser()
    args = parser.parse_args(
        [
            "capture",
            "https://x.com/u/status/1",
            "--out",
            str(tmp_path),
            "--comment-tree",
            "--max-comment-depth",
            "2",
            "--max-comment-visits",
            "5",
        ]
    )

    assert cli._capture(args) == 0
    config = captured["config"]
    assert config.include_comments is True
    assert config.follow_comment_redirects is True
    assert config.comment_tree is True
    assert config.max_comment_depth == 2
    assert config.max_comment_visits == 5


def test_parse_viewport() -> None:
    assert _parse_viewport("1440x900") == (1440, 900)


def test_parse_viewport_rejects_bad_shape() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_viewport("wide")


def test_parse_viewport_rejects_tiny_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_viewport("100x100")

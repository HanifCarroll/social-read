from pathlib import Path

from social_read.browser import (
    PlaywriterDriver,
    _build_job,
    _build_manifest,
    count_sessions,
    parse_new_session_id,
    prepare_paths,
)
from social_read.models import CaptureConfig, SocialPost


def test_parse_new_session_id_from_status_output() -> None:
    output = 'Session 43 created. Use with: playwriter -s 43 -e "..."\n'
    assert parse_new_session_id(output) == "43"


def test_parse_new_session_id_from_plain_output() -> None:
    assert parse_new_session_id("abc-123\n") == "abc-123"


def test_count_sessions() -> None:
    output = "ID  BROWSER\n----------\n1   Chrome\n2   Chrome\n"
    assert count_sessions(output) == 2


def test_parse_result_with_log_prefix() -> None:
    driver = PlaywriterDriver(session="1")
    stdout = '[log] SOCIAL_READ_RESULT {"url":"https://example.com/","ok":true,"post":{}}\n'

    result = driver._parse_result(stdout)

    assert result["ok"] is True


def test_prepare_paths_creates_expected_dirs(tmp_path: Path) -> None:
    paths = prepare_paths(tmp_path / "capture")

    assert paths.screenshot_dir.is_dir()
    assert paths.raw_dir.is_dir()


def test_build_job_includes_comment_tree_options(tmp_path: Path) -> None:
    config = CaptureConfig(
        url="https://x.com/u/status/1",
        output_dir=tmp_path,
        include_comments=True,
        follow_comment_redirects=True,
        comment_tree=True,
        max_comment_depth=3,
        max_comment_visits=7,
    )

    job = _build_job(config, platform="x", post_id="1")

    assert job["includeComments"] is True
    assert job["followCommentRedirects"] is True
    assert job["commentTree"] is True
    assert job["maxCommentDepth"] == 3
    assert job["maxCommentVisits"] == 7


def test_manifest_includes_comment_capture_metadata(tmp_path: Path) -> None:
    config = CaptureConfig(
        url="https://x.com/u/status/1",
        output_dir=tmp_path,
        include_comments=True,
        comment_tree=True,
    )
    paths = prepare_paths(tmp_path)
    post = SocialPost(platform="x", url=config.url)
    raw_result = {
        "ok": True,
        "comment_capture": {
            "requested": True,
            "mode": "tree",
            "complete": False,
            "stopped_reason": "max_comments",
        },
    }

    manifest = _build_manifest(config, post, paths, "2026-07-04T00:00:00Z", raw_result, "1")

    assert manifest["comments_complete"] is False
    assert manifest["comment_capture"]["mode"] == "tree"
    assert manifest["comment_capture"]["stopped_reason"] == "max_comments"

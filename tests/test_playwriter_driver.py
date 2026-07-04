from pathlib import Path

from social_read.browser import (
    PlaywriterDriver,
    count_sessions,
    parse_new_session_id,
    prepare_paths,
)


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

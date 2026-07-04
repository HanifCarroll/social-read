import pytest

from social_read.urls import (
    UnsupportedUrlError,
    default_post_id,
    detect_platform,
    extract_linkedin_post_id,
    extract_x_post_id,
)


def test_detect_platform_for_x_hosts() -> None:
    assert detect_platform("https://x.com/hanif/status/123") == "x"
    assert detect_platform("https://twitter.com/hanif/status/123") == "x"


def test_detect_platform_for_linkedin_hosts() -> None:
    assert (
        detect_platform("https://www.linkedin.com/feed/update/urn:li:activity:123/")
        == "linkedin"
    )
    assert detect_platform("https://www.linkedin.com/posts/example") == "linkedin"


def test_detect_platform_rejects_other_hosts() -> None:
    with pytest.raises(UnsupportedUrlError):
        detect_platform("https://example.com/post")


def test_extract_x_post_id() -> None:
    assert extract_x_post_id("https://x.com/hanif/status/123456789") == "123456789"
    assert extract_x_post_id("https://twitter.com/hanif/statuses/123456789") == "123456789"
    assert extract_x_post_id("https://x.com/hanif") is None


def test_extract_linkedin_post_id_prefers_activity_urn() -> None:
    url = "https://www.linkedin.com/feed/update/urn%3Ali%3Aactivity%3A123456/"
    assert extract_linkedin_post_id(url) == "urn:li:activity:123456"


def test_extract_linkedin_post_id_from_public_post_slug() -> None:
    url = "https://www.linkedin.com/posts/name_title-activity-7358548194995109888-token"
    assert extract_linkedin_post_id(url) == "urn:li:activity:7358548194995109888"


def test_default_post_id_routes_by_platform() -> None:
    assert default_post_id("x", "https://x.com/a/status/42") == "42"
    assert (
        default_post_id("linkedin", "https://www.linkedin.com/feed/update/urn:li:activity:42/")
        == "urn:li:activity:42"
    )

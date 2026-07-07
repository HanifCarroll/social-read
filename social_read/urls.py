from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .models import Platform

X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
LINKEDIN_HOSTS = {"linkedin.com", "www.linkedin.com"}
REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}


class UnsupportedUrlError(ValueError):
    pass


def detect_platform(url: str) -> Platform:
    host = urlparse(url).netloc.lower()
    if host in X_HOSTS:
        return "x"
    if host in LINKEDIN_HOSTS or host.endswith(".linkedin.com"):
        return "linkedin"
    if host in REDDIT_HOSTS or host.endswith(".reddit.com"):
        return "reddit"
    raise UnsupportedUrlError(f"unsupported social URL host: {host or '<missing>'}")


def extract_x_post_id(url: str) -> str | None:
    path = urlparse(url).path
    match = re.search(r"/status(?:es)?/(\d+)", path)
    return match.group(1) if match else None


def extract_linkedin_post_id(url: str) -> str | None:
    decoded = unquote(url)
    activity_match = re.search(r"urn:li:activity:\d+", decoded)
    if activity_match:
        return activity_match.group(0)

    share_match = re.search(r"urn:li:share:\d+", decoded)
    if share_match:
        return share_match.group(0)

    public_activity_match = re.search(r"activity-(\d+)", decoded)
    if public_activity_match:
        return f"urn:li:activity:{public_activity_match.group(1)}"

    path = urlparse(decoded).path.strip("/")
    return path or None


def extract_reddit_post_id(url: str) -> str | None:
    path = urlparse(url).path
    match = re.search(r"/comments/([A-Za-z0-9_]+)/", path)
    return f"t3_{match.group(1)}" if match else None


def default_navigation_url(platform: Platform, url: str) -> str:
    if platform != "reddit":
        return url

    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    host = parsed.netloc.lower()
    if host == "old.reddit.com":
        return url
    if host in REDDIT_HOSTS or host.endswith(".reddit.com"):
        return parsed._replace(netloc="old.reddit.com").geturl()
    return url


def default_post_id(platform: Platform, url: str) -> str | None:
    if platform == "x":
        return extract_x_post_id(url)
    if platform == "reddit":
        return extract_reddit_post_id(url)
    return extract_linkedin_post_id(url)

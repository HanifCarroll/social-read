from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Platform = Literal["linkedin", "x"]


@dataclass
class Author:
    name: str | None = None
    handle: str | None = None
    url: str | None = None


@dataclass
class MediaItem:
    kind: str
    url: str | None = None
    alt: str | None = None


@dataclass
class Comment:
    id: str | None = None
    url: str | None = None
    author: Author = field(default_factory=Author)
    posted_at: str | None = None
    text: str | None = None
    media: list[MediaItem] = field(default_factory=list)
    replies: list[Comment] = field(default_factory=list)
    depth: int | None = None


@dataclass
class SocialPost:
    platform: Platform
    url: str
    final_url: str | None = None
    post_id: str | None = None
    author: Author = field(default_factory=Author)
    posted_at: str | None = None
    text: str | None = None
    media: list[MediaItem] = field(default_factory=list)
    quoted_or_shared_post: dict[str, Any] | None = None
    comments: list[Comment] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CapturePaths:
    output_dir: Path
    manifest: Path
    post_json: Path
    post_md: Path
    screenshot_dir: Path
    raw_dir: Path


@dataclass
class CaptureConfig:
    url: str
    output_dir: Path
    include_comments: bool = False
    max_comments: int | None = None
    max_expansion_rounds: int = 200
    follow_comment_redirects: bool = False
    comment_tree: bool = False
    max_comment_depth: int | None = None
    max_comment_visits: int | None = None
    playwriter_command: str = "playwriter"
    playwriter_session: str = "auto"
    playwriter_browser: str | None = None
    playwriter_direct: str | None = None
    playwriter_patchright: bool = False
    playwriter_proxy: str | None = None
    playwriter_timeout_ms: int = 600_000
    keep_session: bool = False
    timeout_ms: int = 45_000
    wait_ms: int = 1_500
    viewport_width: int = 1440
    viewport_height: int = 1400
    save_html: bool = False


def to_plain(value: Any) -> Any:
    data = asdict(value)
    return _stringify_paths(data)


def _stringify_paths(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _stringify_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_paths(item) for item in value]
    return value

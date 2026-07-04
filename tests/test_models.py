from pathlib import Path

from social_read.models import CapturePaths, to_plain


def test_to_plain_stringifies_paths() -> None:
    paths = CapturePaths(
        output_dir=Path("/tmp/out"),
        manifest=Path("/tmp/out/manifest.json"),
        post_json=Path("/tmp/out/post.json"),
        post_md=Path("/tmp/out/post.md"),
        screenshot_dir=Path("/tmp/out/screenshots"),
        raw_dir=Path("/tmp/out/raw"),
    )

    data = to_plain(paths)

    assert data["output_dir"] == "/tmp/out"
    assert data["manifest"] == "/tmp/out/manifest.json"

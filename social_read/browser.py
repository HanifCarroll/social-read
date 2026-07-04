from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from .extractors import LINKEDIN_EXTRACTION_SCRIPT, X_EXTRACTION_SCRIPT, post_from_raw
from .markdown import render_markdown
from .models import CaptureConfig, CapturePaths, SocialPost, to_plain
from .urls import default_post_id, detect_platform

RESULT_PREFIX = "SOCIAL_READ_RESULT "


class PlaywriterError(RuntimeError):
    pass


def capture(config: CaptureConfig) -> dict[str, Any]:
    platform = detect_platform(config.url)
    post_id = default_post_id(platform, config.url)
    paths = prepare_paths(config.output_dir)
    started_at = datetime.now(UTC).isoformat()
    driver = PlaywriterDriver(
        command=config.playwriter_command,
        session=config.playwriter_session,
        timeout_ms=config.playwriter_timeout_ms,
        new_session_args=_new_session_args(config),
        keep_session=config.keep_session,
    )

    raw_result: dict[str, Any] | None = None
    cleanup_warning: str | None = None
    try:
        raw_result = driver.capture(_build_job(config, platform=platform, post_id=post_id), paths)
    finally:
        cleanup_warning = driver.close()

    raw_post = raw_result.get("post") if isinstance(raw_result.get("post"), dict) else {}
    post = post_from_raw(raw_post, platform=platform, requested_url=config.url, post_id=post_id)
    post.warnings.extend(str(item) for item in raw_result.get("warnings", []) if item)
    _add_redirect_warning(post, platform=platform, requested_url=config.url, post_id=post_id)
    if cleanup_warning:
        post.warnings.append(cleanup_warning)
    post.screenshots.extend(str(item) for item in raw_result.get("screenshots", []) if item)

    if config.include_comments and _count_comments(post) == 0:
        post.warnings.append(
            "Comments were requested, but no comments were captured. "
            "The page may require login, or no replies were loaded."
        )

    _write_post_files(post, paths)
    manifest = _build_manifest(config, post, paths, started_at, raw_result, driver.session)
    paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def prepare_paths(output_dir: Path) -> CapturePaths:
    screenshot_dir = output_dir / "screenshots"
    raw_dir = output_dir / "raw"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    return CapturePaths(
        output_dir=output_dir,
        manifest=output_dir / "manifest.json",
        post_json=output_dir / "post.json",
        post_md=output_dir / "post.md",
        screenshot_dir=screenshot_dir,
        raw_dir=raw_dir,
    )


class PlaywriterDriver:
    def __init__(
        self,
        *,
        command: str = "playwriter",
        session: str = "auto",
        timeout_ms: int = 600_000,
        new_session_args: list[str] | None = None,
        keep_session: bool = False,
    ) -> None:
        self.command = command
        self.session = session
        self.timeout_ms = timeout_ms
        self.new_session_args = new_session_args or []
        self.keep_session = keep_session
        self.created_session = False

    def start(self) -> None:
        if self.session != "auto":
            return
        proc = subprocess.run(
            [self.command, "session", "new", *self.new_session_args],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            message = proc.stderr.strip() or proc.stdout.strip()
            raise PlaywriterError(f"playwriter session new failed: {message}")
        session_id = parse_new_session_id(proc.stdout)
        if not session_id:
            raise PlaywriterError(
                f"could not parse playwriter session id from: {proc.stdout.strip()!r}"
            )
        self.session = session_id
        self.created_session = True

    def capture(self, job: dict[str, Any], paths: CapturePaths) -> dict[str, Any]:
        self.start()
        base_script = (
            files("social_read").joinpath("playwriter_capture.js").read_text(encoding="utf-8")
        )
        temp_dir = Path(tempfile.mkdtemp(prefix="social-read-playwriter-"))
        temp_script = temp_dir / "capture.js"
        payload = {
            **job,
            "fullPageScreenshotPath": str(temp_dir / "full-page.png"),
            "postScreenshotPath": str(temp_dir / "post.png"),
            "htmlPath": str(temp_dir / "rendered.html"),
        }
        temp_script.write_text(
            f"globalThis.SOCIAL_READ_JOB_OBJECT = {json.dumps(payload)};\n{base_script}",
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [
                    self.command,
                    "-s",
                    str(self.session),
                    "--timeout",
                    str(self.timeout_ms),
                    "-f",
                    str(temp_script),
                ],
                cwd=paths.output_dir,
                text=True,
                capture_output=True,
                check=False,
            )
            result = self._parse_result(proc.stdout)
            self._move_temp_artifacts(temp_dir, paths, result)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if proc.returncode != 0:
            process_error = (
                proc.stderr.strip() or proc.stdout.strip() or f"playwriter exited {proc.returncode}"
            )[-4000:]
            if result.get("error"):
                result.setdefault("warnings", []).append(process_error)
            else:
                result["error"] = process_error
            result["ok"] = False
        if result.get("error") and not result.get("post"):
            raise PlaywriterError(str(result["error"]))
        result["session"] = str(self.session)
        return result

    def close(self) -> str | None:
        if not self.created_session or self.keep_session:
            return None
        proc = subprocess.run(
            [self.command, "session", "delete", str(self.session)],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return None
        message = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        return f"Could not delete auto-created Playwriter session {self.session}: {message}"

    def _parse_result(self, stdout: str) -> dict[str, Any]:
        for line in reversed(stdout.splitlines()):
            marker = line.find(RESULT_PREFIX)
            if marker >= 0:
                data = json.loads(line[marker + len(RESULT_PREFIX) :])
                if not isinstance(data, dict):
                    raise PlaywriterError("playwriter returned a non-object result")
                return data
        raise PlaywriterError(
            "playwriter did not return a SOCIAL_READ_RESULT line"
            + (f": {stdout[-4000:]}" if stdout else "")
        )

    def _move_temp_artifacts(
        self, temp_dir: Path, paths: CapturePaths, result: dict[str, Any]
    ) -> None:
        artifact_moves = {
            "fullPageScreenshotFile": (
                temp_dir / "full-page.png",
                paths.screenshot_dir / "full-page.png",
            ),
            "postScreenshotFile": (temp_dir / "post.png", paths.screenshot_dir / "post.png"),
        }
        screenshots: list[str] = []
        for result_key, (source, destination) in artifact_moves.items():
            relative_name = result.get(result_key)
            if not relative_name or not source.exists():
                continue
            shutil.move(str(source), str(destination))
            screenshots.append(str(destination.relative_to(paths.output_dir)))

        if result.get("htmlFile") and (temp_dir / "rendered.html").exists():
            shutil.move(str(temp_dir / "rendered.html"), str(paths.raw_dir / "rendered.html"))

        result["screenshots"] = screenshots


def _build_job(config: CaptureConfig, *, platform: str, post_id: str | None) -> dict[str, Any]:
    return {
        "url": config.url,
        "platform": platform,
        "postId": post_id,
        "includeComments": config.include_comments,
        "maxComments": config.max_comments,
        "maxExpansionRounds": config.max_expansion_rounds,
        "timeoutMs": config.timeout_ms,
        "waitMs": config.wait_ms,
        "viewport": {"width": config.viewport_width, "height": config.viewport_height},
        "saveHtml": config.save_html,
        "xExtractionScript": X_EXTRACTION_SCRIPT,
        "linkedinExtractionScript": LINKEDIN_EXTRACTION_SCRIPT,
    }


def _new_session_args(config: CaptureConfig) -> list[str]:
    args: list[str] = []
    if config.playwriter_browser:
        args.extend(["--browser", config.playwriter_browser])
    if config.playwriter_direct:
        args.append("--direct")
        if config.playwriter_direct != "1":
            args.append(config.playwriter_direct)
    if config.playwriter_patchright:
        args.append("--patchright")
    if config.playwriter_proxy:
        args.extend(["--proxy", config.playwriter_proxy])
    return args


def _write_post_files(post: SocialPost, paths: CapturePaths) -> None:
    paths.post_json.write_text(json.dumps(to_plain(post), indent=2) + "\n", encoding="utf-8")
    paths.post_md.write_text(render_markdown(post), encoding="utf-8")


def _add_redirect_warning(
    post: SocialPost, *, platform: str, requested_url: str, post_id: str | None
) -> None:
    if not post.final_url or post.final_url == requested_url:
        return
    if platform == "x" and post_id and f"/status/{post_id}" not in post.final_url:
        post.warnings.append(
            "X redirected away from the requested status URL before extraction; "
            f"final URL was {post.final_url}."
        )
    if platform == "linkedin" and post_id and not _linkedin_final_url_matches(
        post.final_url, post_id
    ):
        post.warnings.append(
            "LinkedIn redirected away from the requested post URL before extraction; "
            f"final URL was {post.final_url}."
        )


def _linkedin_final_url_matches(final_url: str, post_id: str) -> bool:
    if post_id in final_url:
        return True
    match = re.search(r"(?:activity|share):(\d+)$", post_id)
    return bool(match and match.group(1) in final_url)


def _build_manifest(
    config: CaptureConfig,
    post: SocialPost,
    paths: CapturePaths,
    started_at: str,
    raw_result: dict[str, Any],
    session: str,
) -> dict[str, Any]:
    completed_at = datetime.now(UTC).isoformat()
    return {
        "ok": bool(raw_result.get("ok", True)),
        "tool": "social-read",
        "driver": "playwriter",
        "playwriter_session": session,
        "started_at": started_at,
        "completed_at": completed_at,
        "platform": post.platform,
        "status": raw_result.get("status"),
        "url": config.url,
        "final_url": post.final_url,
        "comments_requested": config.include_comments,
        "comment_count": _count_comments(post),
        "output_dir": str(paths.output_dir),
        "files": {
            "post_json": str(paths.post_json.relative_to(paths.output_dir)),
            "post_md": str(paths.post_md.relative_to(paths.output_dir)),
            "manifest": str(paths.manifest.relative_to(paths.output_dir)),
            "screenshots": post.screenshots,
        },
        "warnings": post.warnings,
    }


def _count_comments(post: SocialPost) -> int:
    def count(items: list[Any]) -> int:
        return sum(1 + count(item.replies) for item in items)

    return count(post.comments)


def doctor(command: str = "playwriter") -> dict[str, Any]:
    path = shutil.which(command)
    if not path:
        return {
            "ok": False,
            "tool": "social-read",
            "driver": "playwriter",
            "command": command,
            "path": None,
            "version": "",
            "session_list_ok": False,
            "active_session_count": 0,
            "warnings": ["playwriter command not found"],
        }

    version = subprocess.run(
        [command, "-v"],
        text=True,
        capture_output=True,
        check=False,
    )
    sessions = subprocess.run(
        [command, "session", "list"],
        text=True,
        capture_output=True,
        check=False,
    )
    warnings = []
    if version.returncode != 0:
        warnings.append(
            version.stderr.strip() or version.stdout.strip() or "playwriter version check failed"
        )
    if sessions.returncode != 0:
        warnings.append(
            sessions.stderr.strip() or sessions.stdout.strip() or "playwriter session list failed"
        )

    return {
        "ok": version.returncode == 0 and sessions.returncode == 0,
        "tool": "social-read",
        "driver": "playwriter",
        "command": command,
        "path": path,
        "version": first_version_line(version.stdout, version.stderr),
        "session_list_ok": sessions.returncode == 0,
        "active_session_count": count_sessions(sessions.stdout) if sessions.returncode == 0 else 0,
        "warnings": warnings,
    }


def count_sessions(output: str) -> int:
    count = 0
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("ID ") or set(stripped) == {"-"}:
            continue
        first = stripped.split(maxsplit=1)[0]
        if first.isdigit() or re.match(r"^[A-Za-z0-9_.:-]+$", first):
            count += 1
    return count


def first_version_line(stdout: str, stderr: str) -> str:
    for line in f"{stdout}\n{stderr}".splitlines():
        stripped = line.strip()
        if stripped.startswith("playwriter/"):
            return stripped
    output = stdout.strip() or stderr.strip()
    return output.splitlines()[0] if output else ""


def parse_new_session_id(output: str) -> str | None:
    match = re.search(r"\bSession\s+([A-Za-z0-9_.:-]+)\s+created\b", output)
    if match:
        return match.group(1)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) == 1 and re.match(r"^[A-Za-z0-9_.:-]+$", lines[0]):
        return lines[0]
    return None

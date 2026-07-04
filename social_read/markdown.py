from __future__ import annotations

from .models import Comment, SocialPost


def render_markdown(post: SocialPost) -> str:
    lines: list[str] = []
    title = _title(post)
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- Platform: {post.platform}")
    lines.append(f"- Source: {post.url}")
    if post.final_url and post.final_url != post.url:
        lines.append(f"- Final URL: {post.final_url}")
    if post.posted_at:
        lines.append(f"- Posted: {post.posted_at}")
    if post.author.name or post.author.handle:
        author_bits = [bit for bit in [post.author.name, post.author.handle] if bit]
        lines.append(f"- Author: {' '.join(author_bits)}")
    if post.author.url:
        lines.append(f"- Author URL: {post.author.url}")
    lines.append("")

    lines.append("## Post")
    lines.append("")
    lines.append(post.text.strip() if post.text else "_No post text captured._")
    lines.append("")

    if post.media:
        lines.append("## Media")
        lines.append("")
        for item in post.media:
            parts = [item.kind]
            if item.alt:
                parts.append(f"alt={item.alt}")
            if item.url:
                parts.append(item.url)
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    if post.quoted_or_shared_post:
        lines.append("## Quoted Or Shared Post")
        lines.append("")
        quoted_text = post.quoted_or_shared_post.get("text")
        quoted_url = post.quoted_or_shared_post.get("url")
        if quoted_text:
            lines.append(str(quoted_text).strip())
        if quoted_url:
            lines.append("")
            lines.append(f"Source: {quoted_url}")
        lines.append("")

    if post.comments:
        lines.append("## Comments")
        lines.append("")
        for index, comment in enumerate(post.comments, start=1):
            _append_comment(lines, comment, index=index, depth=0)

    if post.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in post.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _title(post: SocialPost) -> str:
    platform_name = "LinkedIn" if post.platform == "linkedin" else "X"
    author = post.author.name or post.author.handle
    if author:
        return f"{platform_name} post by {author}"
    return f"{platform_name} post"


def _append_comment(lines: list[str], comment: Comment, *, index: int, depth: int) -> None:
    prefix = "  " * depth
    author = comment.author.name or comment.author.handle or "Unknown author"
    metadata = []
    if comment.posted_at:
        metadata.append(comment.posted_at)
    if comment.url:
        metadata.append(comment.url)
    suffix = f" ({'; '.join(metadata)})" if metadata else ""
    lines.append(f"{prefix}{index}. {author}{suffix}")
    text = comment.text.strip() if comment.text else "_No comment text captured._"
    for line in text.splitlines():
        lines.append(f"{prefix}   {line}")
    if comment.replies:
        for reply_index, reply in enumerate(comment.replies, start=1):
            _append_comment(lines, reply, index=reply_index, depth=depth + 1)
    lines.append("")

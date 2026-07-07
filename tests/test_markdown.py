from social_read.markdown import render_markdown
from social_read.models import Author, Comment, SocialPost


def test_render_markdown_includes_nested_comments_and_warnings() -> None:
    post = SocialPost(
        platform="x",
        url="https://x.com/user/status/1",
        author=Author(name="Test User", handle="@user", url="https://x.com/user"),
        posted_at="2026-07-04T00:00:00Z",
        text="Post body",
        comments=[
            Comment(
                author=Author(name="Commenter"),
                text="First comment",
                replies=[Comment(author=Author(handle="@reply"), text="Nested reply")],
            )
        ],
        warnings=["Partial comments captured."],
    )

    output = render_markdown(post)

    assert "# X post by Test User" in output
    assert "Post body" in output
    assert "1. Commenter" in output
    assert "Nested reply" in output
    assert "Partial comments captured." in output


def test_render_markdown_uses_reddit_title() -> None:
    post = SocialPost(
        platform="reddit",
        url="https://www.reddit.com/r/test/comments/abc/example/",
        author=Author(handle="u/example"),
        text="Post body",
    )

    output = render_markdown(post)

    assert output.startswith("# Reddit post by u/example")

from __future__ import annotations

from typing import Any

from .models import Author, Comment, MediaItem, Platform, SocialPost


def post_from_raw(
    raw: dict[str, Any], *, platform: Platform, requested_url: str, post_id: str | None
) -> SocialPost:
    return _post_from_raw(raw, platform=platform, requested_url=requested_url, post_id=post_id)


def _post_from_raw(
    raw: dict[str, Any], *, platform: Platform, requested_url: str, post_id: str | None
) -> SocialPost:
    warnings = [str(item) for item in raw.get("warnings", []) if item]
    raw_id = raw.get("post_id")
    return SocialPost(
        platform=platform,
        url=requested_url,
        final_url=raw.get("final_url"),
        post_id=raw_id or post_id,
        author=_author_from_raw(raw.get("author")),
        posted_at=raw.get("posted_at"),
        text=raw.get("text"),
        media=[_media_from_raw(item) for item in raw.get("media", [])],
        quoted_or_shared_post=raw.get("quoted_or_shared_post"),
        comments=[_comment_from_raw(item) for item in raw.get("comments", [])],
        warnings=warnings,
    )


def _author_from_raw(raw: dict[str, Any] | None) -> Author:
    raw = raw or {}
    return Author(name=raw.get("name"), handle=raw.get("handle"), url=raw.get("url"))


def _media_from_raw(raw: dict[str, Any]) -> MediaItem:
    return MediaItem(kind=str(raw.get("kind") or "unknown"), url=raw.get("url"), alt=raw.get("alt"))


def _comment_from_raw(raw: dict[str, Any]) -> Comment:
    return Comment(
        id=raw.get("id"),
        url=raw.get("url"),
        author=_author_from_raw(raw.get("author")),
        posted_at=raw.get("posted_at"),
        text=raw.get("text"),
        media=[_media_from_raw(item) for item in raw.get("media", [])],
        replies=[_comment_from_raw(item) for item in raw.get("replies", [])],
        depth=raw.get("depth"),
    )


X_EXTRACTION_SCRIPT = r"""
(options) => {
  const warnings = [];

  const clean = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text.replace(/\u00a0/g, " ").replace(/[ \t\r\f\v]+/g, " ").trim();
    return compact.length ? compact : null;
  };

  const cleanBlock = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text
      .replace(/\u00a0/g, " ")
      .replace(/[ \t\r\f\v]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    return compact.length ? compact : null;
  };

  const absoluteUrl = (href) => {
    if (!href) return null;
    try {
      return new URL(href, document.location.href).href;
    } catch {
      return href;
    }
  };

  const statusIdFromHref = (href) => {
    const match = String(href || "").match(/\/status(?:es)?\/(\d+)/);
    return match ? match[1] : null;
  };

  const metaValue = (selector) => {
    const node = document.querySelector(selector);
    return cleanBlock(node && node.getAttribute("content"));
  };

  const metaDescription = metaValue('meta[property="og:description"], meta[name="description"]');
  const metaUrl = metaValue('meta[property="og:url"]');
  const metaTitle = metaValue('meta[property="og:title"], meta[name="title"]');

  const metaAuthor = () => {
    if (!metaTitle) return {};
    const match = metaTitle.match(/^(.*?)\s+\((@\w+)\)\s+on X$/);
    if (!match) return {};
    const handle = match[2];
    return {
      name: clean(match[1]),
      handle,
      url: `https://x.com/${handle.replace("@", "")}`,
    };
  };

  const articleNodes = Array.from(
    document.querySelectorAll('article[data-tweet-id], article[data-testid="tweet"], article')
  ).filter((node) =>
    node.getAttribute("data-tweet-id") ||
    node.querySelector('[data-testid="tweetText"], time, [data-testid="User-Name"]')
  );

  const hasStatus = (article, id) => {
    if (!id) return false;
    if (article.getAttribute("data-tweet-id") === id) return true;
    return Array.from(article.querySelectorAll('a[href*="/status"]'))
      .some((anchor) => statusIdFromHref(anchor.getAttribute("href")) === id);
  };

  let primary = null;
  if (options.postId) {
    primary = articleNodes.find((article) => hasStatus(article, options.postId)) || null;
  }
  if (!primary && articleNodes.length) {
    primary = articleNodes[0];
    warnings.push(
      "Exact X status article was not found; captured the first tweet article on the page."
    );
  }
  if (!primary) {
    warnings.push("No X tweet article matched the page.");
  }

  const extractAuthor = (article) => {
    const userName = article ? article.querySelector('[data-testid="User-Name"]') : null;
    if (!userName && article && article.getAttribute("data-tweet-id") === options.postId) {
      return metaAuthor();
    }
    const handleText = clean(userName && userName.textContent);
    const handleMatch = handleText ? handleText.match(/@\w+/) : null;
    const handle = handleMatch ? handleMatch[0] : null;
    const spans = userName ? Array.from(userName.querySelectorAll("span")) : [];
    const names = spans
      .map((span) => clean(span.textContent))
      .filter((text) => text && !text.startsWith("@") && text !== "·");
    const links = userName ? Array.from(userName.querySelectorAll("a[href]")) : [];
    const profileLink = links.find((anchor) => {
      const href = anchor.getAttribute("href") || "";
      return href.startsWith("/") && !href.includes("/status") && !href.includes("/photo");
    });
    return {
      name: names.length ? names[0] : null,
      handle,
      url: profileLink ? absoluteUrl(profileLink.getAttribute("href")) : null,
    };
  };

  const tweetText = (article) => {
    if (!article) return null;
    const textNodes = Array.from(article.querySelectorAll('[data-testid="tweetText"]'));
    const parts = textNodes.map((node) => cleanBlock(node.textContent)).filter(Boolean);
    if (parts.length) return parts.join("\n\n");
    if (article.getAttribute("data-tweet-id") === options.postId && metaDescription) {
      return metaDescription;
    }

    const author = extractAuthor(article);
    const articleBlocks = Array.from(article.querySelectorAll('div[dir="auto"]'))
      .filter((node) => !node.closest("a"))
      .map((node) => cleanBlock(node.textContent))
      .filter((value) => {
        if (!value) return false;
        if (value === author.name || value === author.handle) return false;
        return true;
      });
    return articleBlocks.length ? articleBlocks[0] : null;
  };

  const tweetUrl = (article) => {
    if (!article) return null;
    if (article.getAttribute("data-tweet-id") === options.postId && metaUrl) {
      return metaUrl;
    }
    const links = Array.from(article.querySelectorAll('a[href*="/status"]'));
    const exact = options.postId
      ? links.find((anchor) => statusIdFromHref(anchor.getAttribute("href")) === options.postId)
      : null;
    const chosen = exact || links[0] || null;
    return chosen ? absoluteUrl(chosen.getAttribute("href")) : null;
  };

  const tweetId = (article) => {
    if (article && article.getAttribute("data-tweet-id")) {
      return article.getAttribute("data-tweet-id");
    }
    const url = tweetUrl(article);
    return statusIdFromHref(url);
  };

  const extractMedia = (article) => {
    if (!article) return [];
    const items = [];
    const images = Array.from(
      article.querySelectorAll('[data-testid="tweetPhoto"] img, a[href*="/photo/"] img')
    );
    for (const image of images) {
      items.push({
        kind: "image",
        url: image.currentSrc || image.src || null,
        alt: clean(image.alt),
      });
    }
    const videos = Array.from(article.querySelectorAll('[data-testid="videoPlayer"] video, video'));
    for (const video of videos) {
      items.push({ kind: "video", url: video.currentSrc || video.src || null, alt: null });
    }
    return items;
  };

  const postedAt = (article) => {
    const time = article ? article.querySelector("time") : null;
    if (time) return time.getAttribute("datetime");
    const id = tweetId(article);
    const link = id
      ? Array.from(article.querySelectorAll('a[href*="/status"]'))
          .find((anchor) => statusIdFromHref(anchor.getAttribute("href")) === id)
      : null;
    return clean(link && link.textContent);
  };

  const extractArticle = (article, depth = 0) => ({
    id: tweetId(article),
    url: tweetUrl(article),
    author: extractAuthor(article),
    posted_at: postedAt(article),
    text: tweetText(article),
    media: extractMedia(article),
    replies: [],
    depth,
  });

  const quotedArticle = primary
    ? Array.from(primary.querySelectorAll('article[data-testid="tweet"], article'))
        .find((article) => article !== primary && article.closest("article") === primary)
    : null;

  const comments = [];
  if (options.includeComments && primary) {
    const primaryIndex = articleNodes.indexOf(primary);
    const seen = new Set([tweetId(primary)]);
    if (quotedArticle) {
      seen.add(tweetId(quotedArticle));
    }
    for (const article of articleNodes.slice(primaryIndex + 1)) {
      if (primary.contains(article)) continue;
      const id = tweetId(article);
      if (id && seen.has(id)) continue;
      const comment = extractArticle(article, 0);
      if (comment.text || comment.author.name || comment.author.handle) {
        comments.push(comment);
        if (id) seen.add(id);
      }
      if (options.maxComments && comments.length >= options.maxComments) break;
    }
  }

  const post = primary ? extractArticle(primary, 0) : {};
  return {
    final_url: document.location.href,
    post_id: post.id || options.postId || null,
    author: post.author || {},
    posted_at: post.posted_at || null,
    text: post.text || null,
    media: post.media || [],
    quoted_or_shared_post: quotedArticle ? extractArticle(quotedArticle, 0) : null,
    comments,
    warnings,
  };
}
"""


REDDIT_EXTRACTION_SCRIPT = r"""
(options) => {
  const warnings = [];

  const clean = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text.replace(/\u00a0/g, " ").replace(/[ \t\r\f\v]+/g, " ").trim();
    return compact.length ? compact : null;
  };

  const cleanBlock = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text
      .replace(/\u00a0/g, " ")
      .replace(/[ \t\r\f\v]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    return compact.length ? compact : null;
  };

  const absoluteUrl = (href) => {
    if (!href) return null;
    try {
      return new URL(href, document.location.href).href;
    } catch {
      return href;
    }
  };

  const blockText = (root) => {
    if (!root) return null;
    const parts = [];
    const walk = (node) => {
      if (!node) return;
      if (node.nodeType === Node.TEXT_NODE) {
        parts.push(node.nodeValue || "");
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const tag = node.tagName.toLowerCase();
      if (["br", "p", "li", "blockquote", "div"].includes(tag)) parts.push("\n");
      for (const child of Array.from(node.childNodes)) walk(child);
      if (["p", "li", "blockquote", "div"].includes(tag)) parts.push("\n");
    };
    walk(root);
    return cleanBlock(parts.join(""));
  };

  const directChild = (node, className) =>
    Array.from(node ? node.children : []).find((child) => child.classList.contains(className)) ||
    null;

  const commentKey = (comment) =>
    [
      comment.url || "",
      comment.author && comment.author.handle ? comment.author.handle : "",
      comment.posted_at || "",
      comment.text || "",
    ].join("|");
  const redditHandle = (name) => (name ? `/u/${name.replace(/^\/?u\//, "")}` : null);
  const redditThingId = (value) => {
    const text = clean(value);
    return text ? text.replace(/^thing_/, "") : null;
  };

  const post = document.querySelector('.thing.link[data-fullname^="t3_"]');
  if (!post) warnings.push("No old.reddit post container matched .thing.link[data-fullname].");

  const postEntry = directChild(post, "entry") || post;
  const titleNode = postEntry ? postEntry.querySelector("a.title") : null;
  const title = clean(titleNode && titleNode.textContent);
  if (!title) warnings.push("No Reddit post title was captured from a.title.");

  const bodyNode = postEntry ? postEntry.querySelector(".usertext-body .md") : null;
  const body = blockText(bodyNode);
  if (!body) warnings.push("No Reddit post body text was captured from .usertext-body .md.");

  const authorNode = postEntry ? postEntry.querySelector(".tagline a.author") : null;
  const timeNode = postEntry ? postEntry.querySelector(".tagline time") : null;
  const commentsLink = postEntry ? postEntry.querySelector('a.comments[href]') : null;
  const subredditNode = document.querySelector(".pagename a");

  const postText = [title, body].filter(Boolean).join("\n\n") || null;
  const postId = post ? redditThingId(post.getAttribute("data-fullname")) : options.postId || null;

  const extractComment = (node) => {
    const entry = directChild(node, "entry") || node;
    const commentAuthor = entry.querySelector(".tagline a.author");
    const commentTime = entry.querySelector(".tagline time");
    const permalink = entry.querySelector('a.bylink[href]');
    const textNode = entry.querySelector(".usertext-body .md");
    const id = redditThingId(node.getAttribute("data-fullname") || node.getAttribute("id"));
    return {
      id,
      url: absoluteUrl(permalink && permalink.getAttribute("href")),
      author: {
        name: clean(commentAuthor && commentAuthor.textContent),
        handle: redditHandle(clean(commentAuthor && commentAuthor.textContent)),
        url: absoluteUrl(commentAuthor && commentAuthor.getAttribute("href")),
      },
      posted_at: commentTime ? commentTime.getAttribute("datetime") : null,
      text: blockText(textNode),
      media: [],
      replies: [],
      depth: 0,
    };
  };

  const comments = [];
  if (options.includeComments) {
    let commentNodes = Array.from(document.querySelectorAll(".commentarea .thing.comment"));
    const originalCount = commentNodes.length;
    if (options.maxComments && commentNodes.length > Number(options.maxComments)) {
      commentNodes = commentNodes.slice(0, Number(options.maxComments));
      warnings.push(`Stopped Reddit comment extraction after maxComments=${options.maxComments}.`);
    }

    const commentsById = new Map();
    const parentById = new Map();
    for (const node of commentNodes) {
      const comment = extractComment(node);
      const parentNode = node.parentElement ? node.parentElement.closest(".thing.comment") : null;
      const parentId = parentNode
        ? redditThingId(parentNode.getAttribute("data-fullname") || parentNode.getAttribute("id"))
        : null;
      const id = comment.id || commentKey(comment);
      commentsById.set(id, comment);
      parentById.set(id, parentId);
    }

    for (const node of commentNodes) {
      const id = redditThingId(node.getAttribute("data-fullname") || node.getAttribute("id"));
      const comment = commentsById.get(id);
      if (!comment) continue;
      const parentId = parentById.get(id);
      const parent = parentId ? commentsById.get(parentId) : null;
      if (parent) {
        comment.depth = (parent.depth || 0) + 1;
        parent.replies.push(comment);
      } else {
        comment.depth = 0;
        comments.push(comment);
      }
    }

    if (originalCount === 0) {
      warnings.push("Comments were requested, but no old.reddit comments were present.");
    }
    if (document.querySelector(".morecomments")) {
      warnings.push(
        "Reddit page indicates additional comments were not loaded in the static page."
      );
    }
  }

  return {
    final_url: document.location.href,
    post_id: postId,
    author: {
      name: clean(authorNode && authorNode.textContent),
      handle: redditHandle(clean(authorNode && authorNode.textContent)),
      url: absoluteUrl(authorNode && authorNode.getAttribute("href")),
    },
    posted_at: timeNode ? timeNode.getAttribute("datetime") : null,
    subreddit: clean(subredditNode && subredditNode.textContent),
    text: postText,
    media: [],
    quoted_or_shared_post: null,
    comments,
    url: absoluteUrl(commentsLink && commentsLink.getAttribute("href")) || options.requestedUrl,
    warnings,
  };
}
"""


LINKEDIN_EXTRACTION_SCRIPT = r"""
(options) => {
  const warnings = [];

  const clean = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text.replace(/\u00a0/g, " ").replace(/[ \t\r\f\v]+/g, " ").trim();
    return compact.length ? compact : null;
  };

  const cleanBlock = (value) => {
    const text = value == null ? "" : String(value);
    const compact = text
      .replace(/\u00a0/g, " ")
      .replace(/[ \t\r\f\v]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    return compact.length ? compact : null;
  };

  const absoluteUrl = (href) => {
    if (!href) return null;
    try {
      return new URL(href, document.location.href).href;
    } catch {
      return href;
    }
  };

  const firstText = (root, selectors) => {
    if (!root) return null;
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      const value = cleanBlock(node && node.textContent);
      if (value) return value;
    }
    return null;
  };

  const firstUrl = (root, selectors) => {
    if (!root) return null;
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      const href = node && node.getAttribute("href");
      if (href) return absoluteUrl(href);
    }
    return null;
  };

  const socialPosting = () => {
    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
    for (const script of scripts) {
      try {
        const parsed = JSON.parse(script.textContent || "{}");
        const items = Array.isArray(parsed) ? parsed : [parsed];
        const posting = items.find((item) => item && item["@type"] === "SocialMediaPosting");
        if (posting) return posting;
      } catch {
        continue;
      }
    }
    return null;
  };

  const schema = socialPosting();

  const schemaImages = (image) => {
    if (!image) return [];
    const images = Array.isArray(image) ? image : [image];
    return images
      .map((item) => {
        if (typeof item === "string") return { kind: "image", url: item, alt: null };
        if (item && item.url) return { kind: "image", url: item.url, alt: item.caption || null };
        return null;
      })
      .filter(Boolean);
  };

  const schemaComments = () => {
    if (!schema || !options.includeComments) return [];
    const comments = Array.isArray(schema.comment)
      ? schema.comment
      : schema.comment
        ? [schema.comment]
        : [];
    return comments
      .map((comment) => ({
        id: comment["@id"] || null,
        url: comment.url || null,
        author: {
          name: comment.author && comment.author.name ? comment.author.name : null,
          handle: null,
          url: comment.author && comment.author.url ? comment.author.url : null,
        },
        posted_at: comment.datePublished || null,
        text: cleanBlock(comment.text),
        media: [],
        replies: [],
        depth: 0,
      }))
      .filter((comment) => comment.text || comment.author.name || comment.author.url);
  };

  const findPostRoot = () => {
    const candidates = Array.from(
      document.querySelectorAll(
        "article[data-activity-urn], article[data-featured-activity-urn], " +
          "[data-urn], [data-id], article.main-feed-activity-card, " +
          ".feed-shared-update-v2, main"
      )
    );
    if (options.postId) {
      const exact = candidates.find((node) =>
        [
          node.getAttribute("data-activity-urn"),
          node.getAttribute("data-featured-activity-urn"),
          node.getAttribute("data-attributed-urn"),
          node.getAttribute("data-urn"),
          node.getAttribute("data-id"),
          node.id,
        ]
          .filter(Boolean)
          .includes(options.postId)
      );
      if (exact) {
        return exact.closest("article.main-feed-activity-card, .feed-shared-update-v2") || exact;
      }
    }
    const publicCard = document.querySelector("article.main-feed-activity-card");
    if (publicCard) return publicCard;
    const update = document.querySelector(".feed-shared-update-v2");
    if (update) return update;
    const main = document.querySelector("main");
    if (main) {
      warnings.push("LinkedIn update container was not found; captured from main content.");
      return main;
    }
    warnings.push("LinkedIn main content was not found.");
    return document.body;
  };

  const root = findPostRoot();

  const schemaAuthor = schema && schema.author ? schema.author : {};
  const author = {
    name:
      (schemaAuthor && schemaAuthor.name) ||
      firstText(root, [
        ".update-components-actor__title span[aria-hidden='true']",
        ".feed-shared-actor__name span[aria-hidden='true']",
        '[data-test-id="main-feed-activity-card__entity-lockup"] ' +
          'a[aria-label] span[aria-hidden="true"]',
        '[data-tracking-control-name="public_post_feed-actor-name"]',
        '[data-test-id="main-feed-activity-card__entity-lockup"] a[aria-label]',
        ".update-components-actor__name",
        ".feed-shared-actor__name",
        ".update-components-actor__title",
      ]),
    handle: null,
    url:
      (schemaAuthor && schemaAuthor.url) ||
      firstUrl(root, [
        '[data-tracking-control-name="public_post_feed-actor-name"][href]',
        ".update-components-actor__container a[href]",
        ".feed-shared-actor__container-link[href]",
        'a[href*="/in/"]',
        'a[href*="/company/"]',
      ]),
  };

  const postText =
    cleanBlock(schema && schema.articleBody) ||
    firstText(root, [
      '[data-test-id="main-feed-activity-card__commentary"]',
      ".attributed-text-segment-list__content",
      ".feed-shared-update-v2__description",
      ".update-components-text",
      ".feed-shared-text",
      ".break-words",
    ]);

  if (!postText) {
    warnings.push("LinkedIn post text selector did not match.");
  }

  const postId =
    (root &&
      (root.getAttribute("data-activity-urn") ||
        root.getAttribute("data-featured-activity-urn") ||
        root.getAttribute("data-urn") ||
        root.getAttribute("data-id") ||
        root.id)) ||
    options.postId ||
    null;

  const timeNode = root ? root.querySelector("time") : null;
  const postedAtText =
    (timeNode && timeNode.getAttribute("datetime")) ||
    firstText(root, [
      ".update-components-actor__sub-description .visually-hidden",
      ".feed-shared-actor__sub-description .visually-hidden",
      ".update-components-actor__sub-description span[aria-hidden='true']",
      ".feed-shared-actor__sub-description span[aria-hidden='true']",
      ".update-components-actor__sub-description",
      ".feed-shared-actor__sub-description",
    ]);

  let media = schemaImages(schema && schema.image);
  if (root) {
    for (const image of Array.from(root.querySelectorAll(".update-components-image img"))) {
      const src = image.currentSrc || image.src || null;
      if (src) media.push({ kind: "image", url: src, alt: clean(image.alt) });
    }
    for (const video of Array.from(root.querySelectorAll("video"))) {
      media.push({ kind: "video", url: video.currentSrc || video.src || null, alt: null });
    }
  }

  const commentNodes = options.includeComments
    ? Array.from(
        document.querySelectorAll(
          ".comments-comment-item, .comments-comment-entity, [data-test-id='comment']"
        )
      )
    : [];

  const uniqueCommentNodes = [];
  const seenNodes = new Set();
  for (const node of commentNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    uniqueCommentNodes.push(node);
  }

  const commentDepth = (node) => {
    const ariaLevel = Number(node.getAttribute("aria-level"));
    if (Number.isFinite(ariaLevel) && ariaLevel > 0) return ariaLevel - 1;
    const className = String(node.className || "");
    if (className.includes("reply")) return 1;
    const parentReplies = node.closest(".comments-replies-list, .comments-comment-item__replies");
    return parentReplies ? 1 : 0;
  };

  const extractComment = (node) => {
    const profileUrl = firstUrl(node, [
      ".comments-post-meta__profile-link[href]",
      ".comments-comment-meta__image-link[href]",
      'a[href*="/in/"]',
      'a[href*="/company/"]',
    ]);
    const text = firstText(node, [
      ".comments-comment-item__main-content",
      ".comments-comment-item-content-body",
      ".comments-comment-item__comment-text",
      ".comments-comment-item__inline-show-more-text",
      '[data-test-id="commentary"]',
    ]);
    const name = firstText(node, [
      ".comments-post-meta__name-text",
      ".comments-comment-meta__description-title",
      ".comments-comment-meta__name-text",
    ]);
    const time = firstText(node, [
      "time",
      ".comments-comment-meta__data",
      ".comments-post-meta__headline",
    ]);
    return {
      id: node.getAttribute("data-id") || node.getAttribute("data-urn") || node.id || null,
      url: null,
      author: { name, handle: null, url: profileUrl },
      posted_at: time,
      text,
      media: [],
      replies: [],
      depth: commentDepth(node),
    };
  };

  let flatComments = uniqueCommentNodes
    .map(extractComment)
    .filter((comment) => comment.text || comment.author.name || comment.author.url);

  if (options.maxComments) {
    flatComments = flatComments.slice(0, options.maxComments);
  }

  const buildDomCommentTree = (items) => {
    const roots = [];
    const localStack = [];
    for (const comment of items) {
      while (localStack.length && localStack[localStack.length - 1].depth >= comment.depth) {
        localStack.pop();
      }
      if (localStack.length) {
        localStack[localStack.length - 1].replies.push(comment);
      } else {
        roots.push(comment);
      }
      localStack.push(comment);
    }
    return roots;
  };

  const commentKey = (comment) =>
    [
      comment.author && comment.author.name ? comment.author.name : "",
      comment.posted_at || "",
      comment.text || "",
    ].join("|");

  let comments = schemaComments();
  const stack = [];
  const domComments = buildDomCommentTree(flatComments);
  if (!comments.length) {
    comments = domComments;
  } else if (domComments.length) {
    const seenCommentKeys = new Set(comments.map(commentKey));
    for (const comment of domComments) {
      if (!seenCommentKeys.has(commentKey(comment))) {
        comments.push(comment);
        seenCommentKeys.add(commentKey(comment));
      }
    }
  }

  const declaredCommentCount = Number(schema && schema.commentCount);
  if (
    options.includeComments &&
    Number.isFinite(declaredCommentCount) &&
    declaredCommentCount > comments.length
  ) {
    warnings.push(
      `LinkedIn declared ${declaredCommentCount} comments, ` +
        `but only ${comments.length} were captured.`
    );
  }

  return {
    final_url: document.location.href,
    post_id: postId,
    author,
    posted_at: (schema && schema.datePublished) || postedAtText,
    text: postText,
    media,
    quoted_or_shared_post: null,
    comments,
    warnings,
  };
}
"""

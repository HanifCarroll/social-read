const fs = require('node:fs')

const X_TEXT_EXPAND_BUTTONS = [/^(show more|show this thread)$/i]

const X_COMMENT_EXPAND_BUTTONS = [
  /^(show more|show this thread|show replies|show more replies)$/i,
  /^(show additional replies|view replies|view more replies)$/i,
  /^read [\d,.km]+ replies$/i,
]

const LINKEDIN_TEXT_EXPAND_BUTTONS = [/^(see more)$/i]

const LINKEDIN_COMMENT_EXPAND_BUTTONS = [
  /^(see more)$/i,
  /^(load more comments|show more comments|view previous comments)$/i,
  /^(show previous comments|view replies|show replies|load more replies).*$/i,
]

const REDDIT_TEXT_EXPAND_BUTTONS = []
const REDDIT_COMMENT_EXPAND_BUTTONS = []
const REDDIT_MORE_COMMENTS_SELECTOR =
  '.commentarea .thing[data-type="morechildren"] .morecomments > a.button'

function loadJob() {
  if (globalThis.SOCIAL_READ_JOB_OBJECT) return globalThis.SOCIAL_READ_JOB_OBJECT
  const envJob = process.env.SOCIAL_READ_JOB
  if (envJob) return JSON.parse(envJob)
  return JSON.parse(fs.readFileSync('.social-read-job.json', 'utf8'))
}

function warningSink(warnings) {
  const seen = new Set()
  return (message) => {
    if (!message || seen.has(message)) return
    seen.add(message)
    warnings.push(message)
  }
}

function cssString(value) {
  return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function errorMessage(err) {
  return String(err && err.message ? err.message : err)
}

async function main() {
  const job = loadJob()
  const warnings = []
  const warn = warningSink(warnings)
  let status = null
  let error = null
  let rawPost = {}
  let fullPageScreenshotFile = null
  let postScreenshotFile = null
  let htmlFile = null
  const commentCapture = createCommentCapture(job)

  if (!job.url) throw new Error('SOCIAL_READ_JOB.url is required')

  const capturePage = await context.newPage()
  try {
    if (job.viewport) {
      await capturePage.setViewportSize(job.viewport)
    }
    if (job.timeoutMs) {
      capturePage.setDefaultTimeout(job.timeoutMs)
    }

    try {
      const response = await capturePage.goto(job.navigationUrl || job.url, {
        waitUntil: 'domcontentloaded',
        timeout: job.timeoutMs || 45000,
      })
      status = response ? response.status() : null
      if (status !== null && status >= 400) {
        warn(`Initial navigation returned HTTP ${status}.`)
      }
    } catch (err) {
      error = errorMessage(err)
      warn(`Navigation issue: ${error}`)
    }

    await waitForRenderedPage(capturePage, job, warn)
    await expandPostText(capturePage, job.platform, job.waitMs || 1500)
    await detectSignInBlockers(capturePage, job.platform, warn)

    try {
      rawPost = await extractBasePost(capturePage, job, warn)
    } catch (err) {
      error = errorMessage(err)
      warn(`Extraction issue: ${error}`)
    }

    if (job.includeComments) {
      const expansion = await expandComments(capturePage, job, warn)
      applyExpansionResult(commentCapture, expansion)
      if (await detectSignInBlockers(capturePage, job.platform, warn)) {
        markCommentCaptureIncomplete(commentCapture, 'sign_in_blocker')
      }
      if (pageMatchesRequestedPost(capturePage.url(), job.platform, job.postId)) {
        try {
          rawPost = await extractPost(capturePage, job)
        } catch (err) {
          error = errorMessage(err)
          warn(`Extraction issue after comment expansion: ${error}`)
        }
      } else if (job.followCommentRedirects) {
        const redirectedUrl = capturePage.url()
        commentCapture.redirects_followed.push(redirectedUrl)
        warn(
          `${platformName(job.platform)} redirected away while expanding comments; ` +
            'followed the redirect and merged captured comments.'
        )
        try {
          const redirectedPost = await extractPost(capturePage, {
            ...job,
            postId: postIdFromUrl(redirectedUrl, job.platform) || job.postId,
          })
          mergePostComments(rawPost, redirectedPost)
        } catch (err) {
          markCommentCaptureIncomplete(commentCapture, 'redirect_extraction_failed')
          warn(`Extraction issue after following comment redirect: ${errorMessage(err)}`)
        }
      } else {
        markCommentCaptureIncomplete(commentCapture, 'redirect_not_followed')
        warn(
          `${platformName(job.platform)} redirected away while expanding comments; ` +
            'kept the post extraction from before comment expansion.'
        )
      }

      if (job.commentTree) {
        await expandCommentTree(capturePage, rawPost, job, warn, commentCapture)
      }

      await restoreRequestedPost(capturePage, job, warn)
    }

    try {
      await capturePage.screenshot({
        path: job.fullPageScreenshotPath,
        fullPage: true,
        scale: 'css',
      })
      fullPageScreenshotFile = 'screenshots/full-page.png'
    } catch (err) {
      warn(`Full-page screenshot failed: ${errorMessage(err)}`)
    }

    try {
      let locator = primaryPostLocator(capturePage, job.platform, job.postId)
      if (!locator) {
        warn('Primary post screenshot locator was not available.')
      } else {
        if ((await locator.count()) === 0 && job.platform === 'x') {
          const secondaryLocator = capturePage.locator(
            'article[data-tweet-id], article[data-testid="tweet"], article'
          )
          if ((await secondaryLocator.count()) > 0) {
            warn('Exact X post screenshot target was not found; used the first tweet article.')
            locator = secondaryLocator
          }
        }
        if ((await locator.count()) === 0) {
          warn('Primary post screenshot target was not found.')
        } else {
          await locator.first().screenshot({ path: job.postScreenshotPath, scale: 'css' })
          postScreenshotFile = 'screenshots/post.png'
        }
      }
    } catch (err) {
      warn(`Primary post screenshot failed: ${errorMessage(err)}`)
    }

    if (job.saveHtml) {
      try {
        fs.writeFileSync(job.htmlPath, await capturePage.content(), 'utf8')
        htmlFile = 'raw/rendered.html'
      } catch (err) {
        warn(`Rendered HTML save failed: ${errorMessage(err)}`)
      }
    }
  } finally {
    try {
      await capturePage.close()
    } catch {}
  }

  return {
    ok: !error && (status === null || (status >= 200 && status < 400)),
    url: job.url,
    final_url: rawPost && rawPost.final_url ? rawPost.final_url : null,
    status,
    post: rawPost,
    fullPageScreenshotFile,
    postScreenshotFile,
    htmlFile,
    warnings,
    error,
    comment_capture: commentCapture,
  }
}

async function waitForRenderedPage(page, job, warn) {
  try {
    if (typeof waitForPageLoad === 'function') {
      const load = await waitForPageLoad({
        page,
        timeout: Math.min(job.timeoutMs || 45000, 15000),
        minWait: Math.min(job.waitMs || 1500, 1000),
      })
      if (!load || load.success === false) {
        warn(`Load check did not complete cleanly: ${JSON.stringify(load)}`)
      }
      return
    }
    await page.waitForLoadState('networkidle', { timeout: Math.min(job.timeoutMs || 45000, 15000) })
  } catch (err) {
    warn(`Load wait issue: ${errorMessage(err)}`)
  }
}

async function extractPost(page, job) {
  const extractionSource = {
    x: job.xExtractionScript,
    linkedin: job.linkedinExtractionScript,
    reddit: job.redditExtractionScript,
  }[job.platform]
  if (!extractionSource) throw new Error(`Unsupported platform: ${job.platform}`)
  const extractionFunction = eval(extractionSource)
  return await page.evaluate(extractionFunction, {
    requestedUrl: job.url,
    postId: job.postId,
    includeComments: Boolean(job.includeComments),
    maxComments: job.maxComments,
  })
}

async function extractBasePost(page, job, warn) {
  let post = await extractPost(page, job)
  if (pageMatchesRequestedPost(post.final_url || page.url(), job.platform, job.postId)) {
    return post
  }

  warn(
    `${platformName(job.platform)} redirected away before base post extraction; ` +
      'retried the requested post URL.'
  )
  await restoreRequestedPost(page, job, warn)
  post = await extractPost(page, job)
  return post
}

async function expandPostText(page, platform, waitMs) {
  const patterns = {
    x: X_TEXT_EXPAND_BUTTONS,
    linkedin: LINKEDIN_TEXT_EXPAND_BUTTONS,
    reddit: REDDIT_TEXT_EXPAND_BUTTONS,
  }[platform] || []
  for (let round = 0; round < 3; round += 1) {
    const clicked = await clickMatchingButtons(page, patterns, 8)
    if (clicked === 0) return
    await page.waitForTimeout(Math.min(waitMs, 1000))
  }
}

async function expandComments(page, job, warn) {
  if (job.platform === 'reddit') {
    return await expandRedditComments(page, job, warn)
  }

  const patterns = {
    x: X_COMMENT_EXPAND_BUTTONS,
    linkedin: LINKEDIN_COMMENT_EXPAND_BUTTONS,
    reddit: REDDIT_COMMENT_EXPAND_BUTTONS,
  }[job.platform] || []
  let previousSignature = null
  let stableRounds = 0
  const maxRounds = Number(job.maxExpansionRounds || 200)
  const result = { completed: true, rounds: 0, stopped_reason: null }

  for (let round = 0; round < maxRounds; round += 1) {
    result.rounds = round + 1
    const clicked = await clickMatchingButtons(page, patterns, 20)
    await page.mouse.wheel(0, 3000)
    await page.waitForTimeout(Number(job.waitMs || 1500))
    const signature = await pageSignature(page, job.platform)

    if (JSON.stringify(signature) === JSON.stringify(previousSignature) && clicked === 0) {
      stableRounds += 1
    } else {
      stableRounds = 0
    }

    previousSignature = signature
    if (stableRounds >= 3) break
    if (round === maxRounds - 1) {
      result.completed = false
      result.stopped_reason = 'max_expansion_rounds'
      warn(`Stopped comment expansion after ${maxRounds} rounds.`)
    }
  }

  try {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(Math.min(Number(job.waitMs || 1500), 1000))
  } catch {}
  return result
}

async function expandRedditComments(page, job, warn) {
  const maxRounds = Number(job.maxExpansionRounds || 200)
  const result = {
    completed: true,
    rounds: 0,
    clicks: 0,
    reddit_morechildren_remaining: null,
    stopped_reason: null,
  }

  for (let round = 0; round < maxRounds; round += 1) {
    const before = await redditCommentExpansionState(page)
    if (before.morechildren === 0) {
      break
    }

    result.rounds = round + 1
    const clicked = await clickOneRedditMoreCommentsButton(page)
    if (!clicked) {
      result.completed = false
      result.stopped_reason = 'reddit_morecomments_click_failed'
      warn('Stopped Reddit comment expansion because a load-more-comments control could not be clicked.')
      break
    }
    result.clicks += 1

    await waitForRedditMoreCommentsChange(page, before, Number(job.waitMs || 1500))
  }

  const after = await redditCommentExpansionState(page)
  result.reddit_morechildren_remaining = after.morechildren
  if (after.morechildren > 0 && result.completed) {
    result.completed = false
    result.stopped_reason = 'max_expansion_rounds'
    warn(
      `Stopped Reddit comment expansion after ${maxRounds} load-more-comments clicks; ` +
        `${after.morechildren} morechildren controls remain.`
    )
  }

  try {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(Math.min(Number(job.waitMs || 1500), 1000))
  } catch {}
  return result
}

async function redditCommentExpansionState(page) {
  return await page.evaluate((selector) => ({
    comments: document.querySelectorAll('.commentarea .thing.comment').length,
    morechildren: document.querySelectorAll(selector).length,
  }), REDDIT_MORE_COMMENTS_SELECTOR)
}

async function clickOneRedditMoreCommentsButton(page) {
  const locator = page.locator(REDDIT_MORE_COMMENTS_SELECTOR).first()
  try {
    if ((await locator.count()) === 0) return false
    if (!(await locator.isVisible({ timeout: 500 }))) return false
    await locator.click({ timeout: 5000 })
    return true
  } catch {
    return false
  }
}

async function waitForRedditMoreCommentsChange(page, before, waitMs) {
  const timeout = Math.max(5000, Math.min(Number(waitMs || 1500) * 4, 15000))
  try {
    await page.waitForFunction(
      ({ selector, previousComments, previousMorechildren }) => {
        const comments = document.querySelectorAll('.commentarea .thing.comment').length
        const morechildren = document.querySelectorAll(selector).length
        return comments !== previousComments || morechildren !== previousMorechildren
      },
      {
        selector: REDDIT_MORE_COMMENTS_SELECTOR,
        previousComments: before.comments,
        previousMorechildren: before.morechildren,
      },
      { timeout }
    )
  } catch {
    await page.waitForTimeout(Math.min(Number(waitMs || 1500), 2000))
  }
}

async function detectSignInBlockers(page, platform, warn) {
  if (platform === 'reddit') {
    try {
      const title = await page.locator('title').first().textContent({ timeout: 500 })
      if (title && /please wait for verification/i.test(title)) {
        warn('Reddit opened a verification page instead of the public post.')
        return true
      }
    } catch {}
    return false
  }

  const text = platform === 'x'
    ? 'Join X now to read replies on this post'
    : 'Sign in to view more content'
  const warning = platform === 'x'
    ? 'X blocked reply capture behind a login modal.'
    : 'LinkedIn opened a sign-in modal.'

  try {
    const blocker = page.getByText(text)
    if ((await blocker.count()) === 0) return false
    if (!(await blocker.first().isVisible({ timeout: 500 }))) return false
    warn(warning)
  } catch {
    return false
  }

  try {
    const closeButton = page.getByRole('button', { name: /^(close|x|dismiss)$/i })
    if ((await closeButton.count()) > 0) {
      await closeButton.first().click({ timeout: 1200 })
    } else {
      await page.keyboard.press('Escape')
    }
    await page.waitForTimeout(500)
  } catch {
    warn(`Could not close the ${platform} sign-in modal before screenshots.`)
  }
  return true
}

async function clickMatchingButtons(page, patterns, maxClicks) {
  let clicks = 0
  for (const pattern of patterns) {
    if (clicks >= maxClicks) break
    const locator = page.getByRole('button', { name: pattern })
    let count = 0
    try {
      count = await locator.count()
    } catch {
      continue
    }
    for (let index = 0; index < count; index += 1) {
      if (clicks >= maxClicks) break
      const button = locator.nth(index)
      try {
        if (!(await button.isVisible({ timeout: 500 }))) continue
        if (!(await button.isEnabled({ timeout: 500 }))) continue
        await button.click({ timeout: 1200 })
        clicks += 1
        await page.waitForTimeout(250)
      } catch {
        continue
      }
    }
  }
  return clicks
}

async function pageSignature(page, platform) {
  return await page.evaluate((platformValue) => {
    const tweetCount = document.querySelectorAll(
      'article[data-tweet-id], article[data-testid="tweet"], article'
    ).length
    const commentCount = document.querySelectorAll(
      ".comments-comment-item, .comments-comment-entity, [data-test-id='comment']"
    ).length
    return {
      platform: platformValue,
      tweetCount,
      commentCount,
      height: document.documentElement ? document.documentElement.scrollHeight : 0,
      y: window.scrollY,
    }
  }, platform)
}

function primaryPostLocator(page, platform, postId) {
  if (platform === 'x') {
    if (postId) {
      const id = cssString(postId)
      return page
        .locator(`article[data-tweet-id="${id}"], a[href*="/status/${id}"]`)
        .first()
        .locator('xpath=ancestor-or-self::article[1]')
    }
    return page.locator('article[data-tweet-id], article[data-testid="tweet"], article')
  }

  if (platform === 'reddit') {
    if (postId) {
      const id = cssString(postId)
      return page.locator(`.thing.link[data-fullname="${id}"]`)
    }
    return page.locator('.thing.link[data-fullname^="t3_"]')
  }

  if (postId && String(postId).startsWith('urn:li:')) {
    const id = cssString(postId)
    return page.locator(
      `article[data-activity-urn="${id}"], ` +
        `article[data-featured-activity-urn="${id}"], ` +
        `[data-urn="${id}"], [data-id="${id}"]`
    )
  }
  return page.locator('article.main-feed-activity-card, .feed-shared-update-v2, main')
}

function platformName(platform) {
  if (platform === 'linkedin') return 'LinkedIn'
  if (platform === 'reddit') return 'Reddit'
  return 'X'
}

function pageMatchesRequestedPost(url, platform, postId) {
  if (!url || !postId) return true
  if (platform === 'x') return url.includes(`/status/${postId}`)
  if (platform === 'reddit') {
    const redditId = parseRedditThingId(postId)
    if (!redditId.raw) return true
    const pathParts = urlPathParts(url)
    if (redditId.kind === 't3') {
      return pathParts.includes('comments') && pathParts.includes(redditId.raw)
    }
    if (redditId.kind === 't1') {
      return pathParts.includes(redditId.raw) || String(url).includes(redditId.raw)
    }
    return pathParts.includes(redditId.raw) || String(url).includes(redditId.raw)
  }
  if (url.includes(postId)) return true
  const match = String(postId).match(/(?:activity|share):(\d+)$/)
  return Boolean(match && url.includes(match[1]))
}

async function restoreRequestedPost(page, job, warn) {
  try {
    await page.goto(job.navigationUrl || job.url, {
      waitUntil: 'domcontentloaded',
      timeout: job.timeoutMs || 45000,
    })
    await waitForRenderedPage(page, job, warn)
    await expandPostText(page, job.platform, job.waitMs || 1500)
    await detectSignInBlockers(page, job.platform, warn)
  } catch (err) {
    warn(`Could not restore requested post for screenshots: ${errorMessage(err)}`)
  }
}

function createCommentCapture(job) {
  return {
    requested: Boolean(job.includeComments),
    mode: job.commentTree ? 'tree' : 'flat',
    redirect_policy: job.followCommentRedirects ? 'follow' : 'preserve_post',
    max_comment_depth: job.maxCommentDepth ?? null,
    max_comment_visits: job.maxCommentVisits ?? null,
    complete: true,
    stopped_reason: null,
    expansion_rounds: 0,
    expansion_clicks: 0,
    reddit_morechildren_remaining: null,
    redirects_followed: [],
    visited_comment_urls: [],
    visited_comment_count: 0,
  }
}

function applyExpansionResult(commentCapture, result) {
  if (!result) return
  if (Number.isFinite(Number(result.rounds))) {
    commentCapture.expansion_rounds = Number(result.rounds)
  }
  if (Number.isFinite(Number(result.clicks))) {
    commentCapture.expansion_clicks = Number(result.clicks)
  }
  if (Number.isFinite(Number(result.reddit_morechildren_remaining))) {
    commentCapture.reddit_morechildren_remaining = Number(result.reddit_morechildren_remaining)
  }
  if (result.completed === false) {
    markCommentCaptureIncomplete(commentCapture, result.stopped_reason || 'expansion_incomplete')
  }
}

function markCommentCaptureIncomplete(commentCapture, reason) {
  commentCapture.complete = false
  if (!commentCapture.stopped_reason) {
    commentCapture.stopped_reason = reason
  }
}

async function expandCommentTree(page, rootPost, job, warn, commentCapture) {
  if (!rootPost || !Array.isArray(rootPost.comments) || !rootPost.comments.length) {
    return
  }

  const visited = new Set([canonicalUrl(job.url)])
  const queue = []
  enqueueComments(queue, rootPost.comments, 0)

  while (queue.length) {
    if (hasReachedCommentBudget(rootPost, job.maxComments)) {
      markCommentCaptureIncomplete(commentCapture, 'max_comments')
      break
    }
    if (hasReachedVisitBudget(commentCapture, job.maxCommentVisits)) {
      markCommentCaptureIncomplete(commentCapture, 'max_comment_visits')
      break
    }

    const item = queue.shift()
    if (!item || !item.comment || !item.comment.url) continue
    if (isPastMaxDepth(item.depth, job.maxCommentDepth)) continue

    const commentUrl = canonicalUrl(item.comment.url)
    if (!commentUrl || visited.has(commentUrl)) continue
    visited.add(commentUrl)
    commentCapture.visited_comment_urls.push(commentUrl)
    commentCapture.visited_comment_count = commentCapture.visited_comment_urls.length

    const remaining = remainingCommentBudget(rootPost, job.maxComments)
    if (remaining !== null && remaining <= 0) {
      markCommentCaptureIncomplete(commentCapture, 'max_comments')
      break
    }

    const threadPost = await captureThreadReplies(
      page,
      item.comment,
      item.depth,
      job,
      warn,
      commentCapture,
      remaining
    )
    if (!threadPost || !Array.isArray(threadPost.comments)) continue

    const threadReplies = extractThreadReplies(threadPost.comments, item.comment, job.platform)
    const replies = limitComments(threadReplies, remaining)
    setCommentDepths(replies, item.depth + 1)
    item.comment.replies = mergeCommentLists(item.comment.replies || [], replies)
    enqueueComments(queue, item.comment.replies, item.depth + 1)
  }

  rootPost.comments = pruneAncestorDuplicateComments(rootPost.comments || [])
}

async function captureThreadReplies(
  page,
  comment,
  depth,
  job,
  warn,
  commentCapture,
  remainingBudget
) {
  const commentUrl = comment.url
  const threadJob = {
    ...job,
    url: commentUrl,
    postId: normalizeRedditThingId(comment.id) || postIdFromUrl(commentUrl, job.platform),
    maxComments: threadMaxComments(job, remainingBudget),
  }

  try {
    await page.goto(commentUrl, {
      waitUntil: 'domcontentloaded',
      timeout: job.timeoutMs || 45000,
    })
    await waitForRenderedPage(page, threadJob, warn)
    await expandPostText(page, job.platform, job.waitMs || 1500)
    if (await detectSignInBlockers(page, job.platform, warn)) {
      markCommentCaptureIncomplete(commentCapture, 'sign_in_blocker')
      return null
    }

    const expansion = await expandComments(page, threadJob, warn)
    applyExpansionResult(commentCapture, expansion)

    const currentUrl = page.url()
    const stayedOnRequestedComment = canonicalUrl(currentUrl) === canonicalUrl(commentUrl)
    if (!stayedOnRequestedComment && !pageMatchesRequestedPost(currentUrl, job.platform, threadJob.postId)) {
      if (!job.followCommentRedirects) {
        markCommentCaptureIncomplete(commentCapture, 'tree_redirect_not_followed')
        warn(
          `${platformName(job.platform)} redirected away from a comment URL at depth ${depth}; ` +
            'stopped that branch.'
        )
        return null
      }
      commentCapture.redirects_followed.push(currentUrl)
    }

    return await extractPost(page, {
      ...threadJob,
      postId: postIdFromUrl(currentUrl, job.platform) || threadJob.postId,
    })
  } catch (err) {
    markCommentCaptureIncomplete(commentCapture, 'tree_capture_error')
    warn(`Could not capture replies for ${commentUrl}: ${errorMessage(err)}`)
    return null
  }
}

function enqueueComments(queue, comments, depth) {
  for (const comment of comments || []) {
    queue.push({ comment, depth })
  }
}

function isPastMaxDepth(depth, maxDepth) {
  return maxDepth !== null && maxDepth !== undefined && depth >= Number(maxDepth)
}

function mergePostComments(basePost, extraPost) {
  if (!basePost.comments) basePost.comments = []
  if (!extraPost || !Array.isArray(extraPost.comments)) return basePost
  basePost.comments = mergeCommentLists(basePost.comments, extraPost.comments)
  return basePost
}

function extractThreadReplies(comments, parentComment, platform) {
  if (platform !== 'reddit') return comments || []

  const parent = findMatchingComment(comments || [], parentComment)
  if (parent) return removeMatchingComments(parent.replies || [], parentComment)

  return removeMatchingComments(comments || [], parentComment)
}

function findMatchingComment(comments, target) {
  for (const comment of comments || []) {
    if (commentsMatch(comment, target)) return comment
    const nested = findMatchingComment(comment.replies || [], target)
    if (nested) return nested
  }
  return null
}

function removeMatchingComments(comments, target) {
  const output = []
  for (const comment of comments || []) {
    if (commentsMatch(comment, target)) continue
    comment.replies = removeMatchingComments(comment.replies || [], target)
    output.push(comment)
  }
  return output
}

function pruneAncestorDuplicateComments(comments, ancestors = []) {
  const output = []
  for (const comment of comments || []) {
    if (ancestors.some((ancestor) => commentsMatch(comment, ancestor))) continue
    comment.replies = pruneAncestorDuplicateComments(comment.replies || [], [...ancestors, comment])
    output.push(comment)
  }
  return output
}

function commentsMatch(left, right) {
  if (!left || !right) return false
  const leftId = normalizedCommentId(left)
  const rightId = normalizedCommentId(right)
  if (leftId && rightId && leftId === rightId) return true

  const leftUrl = canonicalUrl(left.url)
  const rightUrl = canonicalUrl(right.url)
  if (leftUrl && rightUrl && leftUrl === rightUrl) return true

  return commentKey(left) === commentKey(right)
}

function mergeCommentLists(existing, incoming) {
  const existingByKey = new Map()
  for (const comment of existing || []) {
    existingByKey.set(commentKey(comment), comment)
  }

  for (const comment of incoming || []) {
    const key = commentKey(comment)
    const current = existingByKey.get(key)
    if (current) {
      current.replies = mergeCommentLists(current.replies || [], comment.replies || [])
      continue
    }
    if (!comment.replies) comment.replies = []
    existing.push(comment)
    existingByKey.set(key, comment)
  }
  return existing
}

function commentKey(comment) {
  if (!comment) return ''
  const id = normalizedCommentId(comment)
  if (id) return `id:${id}`
  const url = canonicalUrl(comment.url)
  if (url) return `url:${url}`
  return [
    comment.author && comment.author.name ? comment.author.name : '',
    comment.author && comment.author.handle ? comment.author.handle : '',
    comment.posted_at || '',
    comment.text || '',
  ].join('|')
}

function normalizedCommentId(comment) {
  if (!comment || !comment.id) return ''
  return normalizeRedditThingId(comment.id) || String(comment.id)
}

function countCommentTree(comments) {
  let total = 0
  for (const comment of comments || []) {
    total += 1
    total += countCommentTree(comment.replies || [])
  }
  return total
}

function remainingCommentBudget(rootPost, maxComments) {
  if (!maxComments) return null
  return Math.max(0, Number(maxComments) - countCommentTree(rootPost.comments || []))
}

function hasReachedCommentBudget(rootPost, maxComments) {
  const remaining = remainingCommentBudget(rootPost, maxComments)
  return remaining !== null && remaining <= 0
}

function hasReachedVisitBudget(commentCapture, maxVisits) {
  if (!maxVisits) return false
  return commentCapture.visited_comment_urls.length >= Number(maxVisits)
}

function threadMaxComments(job, remainingBudget) {
  if (job.platform === 'reddit') return null
  return remainingBudget
}

function limitComments(comments, budget) {
  if (budget === null || budget === undefined) return comments || []
  let remaining = Number(budget)
  const output = []
  for (const comment of comments || []) {
    if (remaining <= 0) break
    output.push(comment)
    remaining -= 1
    if (comment.replies && comment.replies.length) {
      comment.replies = limitComments(comment.replies, remaining)
      remaining -= countCommentTree(comment.replies)
    }
  }
  return output
}

function setCommentDepths(comments, depth) {
  for (const comment of comments || []) {
    comment.depth = depth
    setCommentDepths(comment.replies || [], depth + 1)
  }
}

function canonicalUrl(url) {
  if (!url) return null
  try {
    const parsed = new URL(url)
    parsed.hash = ''
    return parsed.href
  } catch {
    return String(url)
  }
}

function normalizeRedditThingId(value) {
  if (!value) return null
  return String(value).replace(/^thing_/, '')
}

function parseRedditThingId(value) {
  const normalized = normalizeRedditThingId(value)
  if (!normalized) return { kind: null, raw: null }
  const match = normalized.match(/^(t[13]_)?([A-Za-z0-9]+)/)
  return {
    kind: match && match[1] ? match[1].replace('_', '') : null,
    raw: match ? match[2] : normalized,
  }
}

function urlPathParts(url) {
  try {
    return new URL(url).pathname.split('/').filter(Boolean)
  } catch {
    return String(url || '').split(/[/?#]/).filter(Boolean)
  }
}

function postIdFromUrl(url, platform) {
  if (platform === 'reddit') {
    const match = String(url || '').match(/\/comments\/[A-Za-z0-9_]+\/[^/]+\/([A-Za-z0-9_]+)/)
    return match ? `t1_${match[1]}` : null
  }
  return statusIdFromUrl(url)
}

function statusIdFromUrl(url) {
  const match = String(url || '').match(/\/status(?:es)?\/(\d+)/)
  return match ? match[1] : null
}

async function runCapture() {
  try {
    const result = await main()
    if (loadJob().resultPath) {
      fs.writeFileSync(loadJob().resultPath, JSON.stringify(result), 'utf8')
      return 'SOCIAL_READ_RESULT_FILE ' + loadJob().resultPath
    }
    return 'SOCIAL_READ_RESULT ' + JSON.stringify(result)
  } catch (err) {
    let url = null
    let resultPath = null
    try {
      const job = loadJob()
      url = job.url
      resultPath = job.resultPath || null
    } catch {}
    const result = {
      ok: false,
      url,
      final_url: null,
      status: null,
      post: {},
      fullPageScreenshotFile: null,
      postScreenshotFile: null,
      htmlFile: null,
      warnings: [],
      error: String(err && err.stack ? err.stack : err),
    }
    if (resultPath) {
      fs.writeFileSync(resultPath, JSON.stringify(result), 'utf8')
      return 'SOCIAL_READ_RESULT_FILE ' + resultPath
    }
    return 'SOCIAL_READ_RESULT ' + JSON.stringify(result)
  }
}

console.log(await runCapture())

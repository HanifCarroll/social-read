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
      const response = await capturePage.goto(job.url, {
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
      rawPost = await extractPost(capturePage, job)
    } catch (err) {
      error = errorMessage(err)
      warn(`Extraction issue: ${error}`)
    }

    if (job.includeComments) {
      await expandComments(capturePage, job, warn)
      await detectSignInBlockers(capturePage, job.platform, warn)
      if (pageMatchesRequestedPost(capturePage.url(), job.platform, job.postId)) {
        try {
          rawPost = await extractPost(capturePage, job)
        } catch (err) {
          error = errorMessage(err)
          warn(`Extraction issue after comment expansion: ${error}`)
        }
      } else {
        warn(
          `${platformName(job.platform)} redirected away while expanding comments; ` +
            'kept the post extraction from before comment expansion.'
        )
        await restoreRequestedPost(capturePage, job, warn)
      }
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
      const locator = primaryPostLocator(capturePage, job.platform, job.postId)
      if (!locator) {
        warn('Primary post screenshot locator was not available.')
      } else if ((await locator.count()) === 0) {
        warn('Primary post screenshot target was not found.')
      } else {
        await locator.first().screenshot({ path: job.postScreenshotPath, scale: 'css' })
        postScreenshotFile = 'screenshots/post.png'
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
  const extractionSource = job.platform === 'x' ? job.xExtractionScript : job.linkedinExtractionScript
  const extractionFunction = eval(extractionSource)
  return await page.evaluate(extractionFunction, {
    requestedUrl: job.url,
    postId: job.postId,
    includeComments: Boolean(job.includeComments),
    maxComments: job.maxComments,
  })
}

async function expandPostText(page, platform, waitMs) {
  const patterns = platform === 'x' ? X_TEXT_EXPAND_BUTTONS : LINKEDIN_TEXT_EXPAND_BUTTONS
  for (let round = 0; round < 3; round += 1) {
    const clicked = await clickMatchingButtons(page, patterns, 8)
    if (clicked === 0) return
    await page.waitForTimeout(Math.min(waitMs, 1000))
  }
}

async function expandComments(page, job, warn) {
  const patterns = job.platform === 'x' ? X_COMMENT_EXPAND_BUTTONS : LINKEDIN_COMMENT_EXPAND_BUTTONS
  let previousSignature = null
  let stableRounds = 0
  const maxRounds = Number(job.maxExpansionRounds || 200)

  for (let round = 0; round < maxRounds; round += 1) {
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
      warn(`Stopped comment expansion after ${maxRounds} rounds.`)
    }
  }

  try {
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(Math.min(Number(job.waitMs || 1500), 1000))
  } catch {}
}

async function detectSignInBlockers(page, platform, warn) {
  const text = platform === 'x'
    ? 'Join X now to read replies on this post'
    : 'Sign in to view more content'
  const warning = platform === 'x'
    ? 'X blocked reply capture behind a login modal.'
    : 'LinkedIn opened a sign-in modal.'

  try {
    const blocker = page.getByText(text)
    if ((await blocker.count()) === 0) return
    if (!(await blocker.first().isVisible({ timeout: 500 }))) return
    warn(warning)
  } catch {
    return
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
  return platform === 'linkedin' ? 'LinkedIn' : 'X'
}

function pageMatchesRequestedPost(url, platform, postId) {
  if (!url || !postId) return true
  if (platform === 'x') return url.includes(`/status/${postId}`)
  if (url.includes(postId)) return true
  const match = String(postId).match(/(?:activity|share):(\d+)$/)
  return Boolean(match && url.includes(match[1]))
}

async function restoreRequestedPost(page, job, warn) {
  try {
    await page.goto(job.url, {
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

async function runCapture() {
  try {
    const result = await main()
    return 'SOCIAL_READ_RESULT ' + JSON.stringify(result)
  } catch (err) {
    let url = null
    try {
      url = loadJob().url
    } catch {}
    return 'SOCIAL_READ_RESULT ' + JSON.stringify({
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
    })
  }
}

console.log(await runCapture())

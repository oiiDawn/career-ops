/** Verify the user-confirmed LinkedIn no-Apply rule only after a matching detail page settles. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { classifyLiveness } from '../../adapters/node/browser/liveness-core.mjs';
import { checkUrlLiveness } from '../../adapters/node/browser/liveness-browser.mjs';
const url = 'https://cn.linkedin.com/jobs/view/engineer-4475675400?trackingId=123456789';
const posting = { url: 'https://cn.linkedin.com/jobs/view/engineer-4475675400', title: 'Engineer', descriptionLength: 500, ready: true };
const valid = { status: 200, requestedUrl: url, finalUrl: url, bodyText: 'Responsibilities. '.repeat(30), linkedinPosting: posting, settled: true };
assert.equal(classifyLiveness(valid).code, 'linkedin_no_apply');
for (const patch of [
  { settled: false }, { status: 403 }, { status: 429 }, { status: 500 },
  { finalUrl: 'https://www.linkedin.com/authwall' }, { linkedinPosting: null },
  { linkedinPosting: { ...posting, ready: false } },
  { linkedinPosting: { ...posting, descriptionLength: 0 } },
  { linkedinPosting: { ...posting, title: '' } },
  { linkedinPosting: { ...posting, url: 'https://cn.linkedin.com/jobs/view/9999999999' } },
  { visibleApplyControls: ['Apply'] },
]) assert.equal(classifyLiveness({ ...valid, ...patch }).result, 'uncertain', JSON.stringify(patch));
assert.equal(classifyLiveness({ ...valid, applyControls: ['Apply'] }).result, 'active');
assert.equal(classifyLiveness({ ...valid, bodyText: 'Verify you are human' }).result, 'uncertain');
const browser = await chromium.launch({ headless: true });
try {
  for (const [extra, expected] of [
    ['', 'expired'],
    ['<script>setTimeout(()=>document.body.insertAdjacentHTML("beforeend","<button>Apply</button>"),3000)</script>', 'active'],
    ['<div class="authwall">Sign in to continue</div>', 'uncertain'],
    ['<button disabled>Apply</button>', 'uncertain'],
  ]) {
    const page = await browser.newPage();
    const navigate = page.goto.bind(page);
    page.goto = async (...args) => {
      await page.route(url, route => route.fulfill({ contentType: 'text/html', body:
      `<link rel="canonical" href="${posting.url}"><h1 class="topcard__title">Engineer</h1><section class="description__text"><div class="show-more-less-html__markup">${valid.bodyText}</div></section>${extra}` }));
      return navigate(...args);
    };
    const result = await checkUrlLiveness(page, url);
    assert.equal(result.result, expected, JSON.stringify(result));
    if (expected === 'expired') {
      assert.equal(result.code, 'linkedin_no_apply');
      assert.equal(result.evidence.settled, true);
      assert.equal(result.evidence.posting_id, '4475675400');
    }
    await page.close();
  }
} finally { await browser.close(); }
console.log('LinkedIn UI: complete identity-bound no-Apply closure, late Apply and login-wall safety passed');

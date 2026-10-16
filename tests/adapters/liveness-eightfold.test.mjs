/** Verify the trusted Eightfold-to-ATS identity chain before accepting an application page. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { resolveEightfoldApplication } from '../../adapters/node/browser/liveness-api.mjs';
import { checkUrlLiveness } from '../../adapters/node/browser/liveness-browser.mjs';
const url = 'https://portal.careers.hsbc.com/careers/job/563774612370937';
const target = 'https://career2.successfactors.eu/careers?company=hsbcholdin&career_ns=job_application&career_job_req_id=61724';
const valid = { id: 563774612370937, ats_job_id: '61724', apply_redirect_url: target };
const originalFetch = globalThis.fetch;
let browser;
try {
  for (const payload of [
    { ...valid, id: 1 }, { ...valid, ats_job_id: '99999' },
    { ...valid, apply_redirect_url: target.replace('career2.successfactors.eu', 'example.com') },
    { ...valid, apply_redirect_url: target.replace('job_application', 'job_search') },
    { ...valid, apply_redirect_url: target.replace('https:', 'http:') },
  ]) {
    globalThis.fetch = async () => Response.json(payload);
    assert.equal(await resolveEightfoldApplication(url), null);
  }
  globalThis.fetch = async (endpoint, options) => {
    assert.equal(endpoint, 'https://portal.careers.hsbc.com/api/apply/v2/jobs/563774612370937');
    assert.equal(options.redirect, 'error');
    return Response.json(valid);
  };
  assert.deepEqual(await resolveEightfoldApplication(url), { url: target, jobId: '61724' });
  assert.equal(await resolveEightfoldApplication(url.replace('hsbc.com', 'hsbc.com.example.org')), null);
  browser = await chromium.launch({ headless: true });
  for (const [heading, button, expected, hidden = false] of [
    ['Senior Software Engineer (61724)', '<button>Apply</button>', 'active'],
    ['Other Job (99999)', '<button>Apply</button>', 'uncertain'],
    ['Senior Software Engineer (61724)', '<button hidden>Apply</button>', 'uncertain'],
    ['Senior Software Engineer (61724)', '<button>Apply</button>', 'uncertain', true],
  ]) {
    const page = await browser.newPage();
    const navigate = page.goto.bind(page);
    page.goto = async (...args) => {
      await page.route(url, route => route.fulfill({ contentType: 'text/html', body: '<h1>Engineer</h1>' + '<p>Responsibilities and requirements.</p>'.repeat(15) }));
      await page.route(target, route => route.fulfill({ contentType: 'text/html', body: `<h1 ${hidden ? 'hidden' : ''}>${heading}</h1>${button}` + '<p>Candidate application form.</p>'.repeat(15) }));
      return navigate(...args);
    };
    const result = await checkUrlLiveness(page, url);
    assert.equal(result.result, expected, JSON.stringify({result, url:page.url(), headings:await page.locator('h1').allTextContents()}));
    if (expected === 'active') assert.equal(result.evidence.posting_url, url);
    await page.close();
  }
  globalThis.fetch = async () => new Response('', { status: 403 });
  assert.equal(await resolveEightfoldApplication(url), null);
} finally {
  globalThis.fetch = originalFetch;
  await browser?.close();
}
console.log('Eightfold: trusted application URL, matching ATS heading and visible Apply required');

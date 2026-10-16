/** Verify application and closure signals from observed ATS layouts without network access. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { checkLivenessViaApi, classifyLinkedInPosting } from '../../adapters/node/browser/liveness-api.mjs';
import { classifyLiveness } from '../../adapters/node/browser/liveness-core.mjs';
import { checkUrlLiveness } from '../../adapters/node/browser/liveness-browser.mjs';

const url = 'https://jobs.smartrecruiters.com/BoschGroup/744000146938409-engineer';
const originalFetch = globalThis.fetch;
try {
  for (const [payload, expected] of [
    [{ id: '744000146938409', active: true, visibility: 'PUBLIC', applyUrl: url + '?oga=true' }, 'active'],
    [{ id: 'other', active: true, visibility: 'PUBLIC', applyUrl: url }, undefined],
    [{ id: '744000146938409', active: false, visibility: 'PUBLIC', applyUrl: url }, undefined],
    [{ id: '744000146938409', active: true, visibility: 'PUBLIC', applyUrl: 'https://example.com/' }, undefined],
  ]) {
    globalThis.fetch = async () => new Response(JSON.stringify(payload));
    assert.equal((await checkLivenessViaApi(url))?.result, expected);
  }
  globalThis.fetch = async () => new Response('', { status: 403 });
  assert.equal(await checkLivenessViaApi(url), null);
} finally { globalThis.fetch = originalFetch; }
assert.equal(classifyLinkedInPosting('<figcaption class="closed-job__flavor--closed">已停止接受求职申请</figcaption>').result, 'expired');
assert.equal(classifyLinkedInPosting('<figcaption>已停止接受求职申请</figcaption><button data-modal="job-details-topcard-apply-modal">申请</button>').result, 'uncertain');
assert.equal(classifyLiveness({ status: 200, bodyText: "The page you are looking for doesn't exist." }).result, 'uncertain');

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const navigate = page.goto.bind(page);
  const fixtures = [
    ['https://jobs.smartrecruiters.com/BoschGroup/744000146938409-engineer', '<a data-sr-track="apply" href="https://jobs.smartrecruiters.com/oneclick-ui/company/BoschGroup/publication/example">I\'m interested</a>', 'active'],
    ['https://cn.linkedin.com/jobs/view/4475675400', '<button data-modal="job-details-topcard-apply-modal">申请</button>', 'active'],
    ['https://cn.linkedin.com/jobs/view/4469654437', '<figcaption class="closed-job__flavor--closed">已停止接受求职申请</figcaption>', 'expired'],
    ['https://cn.linkedin.com/jobs/view/4469654437', '<figcaption>已停止接受求职申请</figcaption><button data-modal="job-details-topcard-apply-modal">申请</button>', 'uncertain'],
    ['https://jobs.mercedes-benz.com/engineer-183318-MER0003THB', '<wb-button href="https://tas-daimler.taleo.net/careersection/ex/jobapply.ftl?job=MER0003THB" aria-label="Bewerben" style="display:inline-block">Bewerben</wb-button>', 'active'],
    ['https://careers.abb/global/en/job/JR00043431', '<div id="job">Loading</div><script>setTimeout(()=>document.querySelector("#job").innerHTML="<button>Apply now</button>",2300)</script>', 'active'],
    ['https://cn.linkedin.com/jobs/view/4475675400', '<button disabled data-modal="job-details-topcard-apply-modal">申请</button><button hidden>Apply</button>', 'uncertain'],
    ['https://example.com/job/1234567', '<button>申请记录</button>', 'uncertain'],
  ];
  for (const [posting, html, expected] of fixtures) {
    page.goto = async () => {
      await page.route(posting, route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<main>' + 'Responsibilities and qualifications. '.repeat(12) + html + '</main>' }));
      return navigate(posting);
    };
    const result = await checkUrlLiveness(page, posting);
    assert.equal(result.result, expected, posting + ' ' + JSON.stringify(result));
    if (expected === 'expired') assert.equal(result.evidence.excerpt, '已停止接受求职申请');
  }
} finally { await browser.close(); }
console.log('observed liveness layouts: API identity, localized controls, hydration and closure passed');

/** Exercise one coherent browser snapshot and preserve the classifier's actual closure evidence. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { classifyLiveness } from '../../adapters/node/browser/liveness-core.mjs';
import { checkUrlLiveness } from '../../adapters/node/browser/liveness-browser.mjs';

for (const weak of ['Applications are closed.', 'Closed on 12 October 2026.']) {
  assert.equal(classifyLiveness({ status: 200, bodyText: weak }).result, 'uncertain',
    'A generic closure phrase without a posting-specific assertion cannot authorize deletion');
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const navigate = page.goto.bind(page);
  const closed = 'https://careers.example.com/job/1234567';
  page.goto = async () => {
    await page.route(closed, route => route.fulfill({ contentType: 'text/html; charset=utf-8',
      body: '<h1>Engineer</h1><p>Job posting has expired</p>' }));
    return navigate(closed);
  };
  const result = await checkUrlLiveness(page, closed);
  assert.equal(result.result, 'expired');
  assert.equal(result.evidence.excerpt, 'Job posting has expired', 'The classified closure must carry its own evidence');

  const framed = 'https://careers.example.com/job/7654321';
  page.goto = async () => {
    await page.route(framed + '/detail', route => route.fulfill({ contentType: 'text/html; charset=utf-8',
      body: '<div id="job">Loading</div><script>setTimeout(()=>document.querySelector("#job").innerHTML="<button>Apply now</button>",2500)</script>' }));
    await page.route(framed, route => route.fulfill({ contentType: 'text/html; charset=utf-8',
      body: '<main>' + 'Responsibilities and qualifications. '.repeat(12) + `<iframe src="${framed}/detail"></iframe></main>` }));
    return navigate(framed);
  };
  const hydrated = await checkUrlLiveness(page, framed);
  assert.equal(hydrated.result, 'active', 'A late application control in a same-origin frame must be observed');
} finally { await browser.close(); }
console.log('liveness snapshot: closure evidence and late same-origin application controls passed');

/** Exercise delayed Workday hydration through the production browser extraction path. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readPage } from '../browser-extract.mjs';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route('https://fixture.myworkdayjobs.com/**', route => route.fulfill({
    contentType: 'text/html', body: `<html><body><h1>Accept Cookies</h1><main>Loading</main><script>
      setTimeout(() => { document.title = 'Engineer'; document.querySelector('main').innerHTML = '<h2>Engineer</h2><div data-automation-id="jobPostingDescription"><p>Full responsibilities and qualifications.</p><p>Build reliable products.</p></div>'; }, 2300);
    </script></body></html>`,
  }));
  await page.goto('https://fixture.myworkdayjobs.com/Jobs/job/Engineer_R1');
  const result = await readPage(page, { timeout: 4000 });
  assert(result.text.includes('Full responsibilities and qualifications.'), 'Must wait for the JD, not return the Loading shell');
  assert.equal(result.title, 'Engineer');
  assert(result.text.includes('qualifications.\nBuild reliable products.'), 'Paragraph boundaries must survive DOM cloning');
  await page.setContent('<main>Loading</main>');
  await assert.rejects(readPage(page, { timeout: 100 }), /Timeout/);
  await page.setContent('<main>This job is no longer available.</main>');
  assert((await readPage(page, { timeout: 100 })).text.includes('no longer available'));
} finally { await browser.close(); }
console.log('browser-extract: delayed Workday JD is extracted');

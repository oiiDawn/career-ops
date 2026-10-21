/** Verify scan handoff reuse, expiry and failed-page fallback without network access. */
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { captureScanJds, extractPosting, readScanJd, scanJdPath, samePostingUrl, JD_MAX_AGE_MS } from '../../adapters/node/browser/scan-jd.mjs';
import { readJobsdbPosting } from '../../adapters/node/providers/jobstreet.mjs';
const root = mkdtempSync(join(tmpdir(), 'scan-jd-'));
try {
  assert.equal(scanJdPath('https://example.com/jobs/123', root).startsWith(join(root, 'cache', 'scan-jds')), true);
  const offer = { url: 'https://example.com/jobs/123' };
  let calls = 0;
  const extract = async url => { calls++; return { url, title: 'Engineer', text: 'Responsibilities and qualifications' }; };
  assert.deepEqual(await captureScanJds([offer, offer], root, extract), { captured: 1, reused: 0, failed: 0 });
  assert.equal(readScanJd(offer.url, root).text, 'Responsibilities and qualifications');
  const cli = spawnSync(process.execPath, [fileURLToPath(new URL('../../adapters/node/browser/scan-jd.mjs', import.meta.url)), offer.url, root], { encoding: 'utf8' });
  assert.equal(cli.status, 0, cli.stderr);
  assert.equal(JSON.parse(cli.stdout).snapshot.text, 'Responsibilities and qualifications');
  assert.equal((await captureScanJds([offer], root, extract)).reused, 1);
  assert.equal(calls, 1);
  assert.equal((await captureScanJds([offer], root, extract, true)).captured, 1);
  assert.equal(calls, 2);
  const moka = { url: 'https://app.mokahr.com/social-recruitment/step/94904#/job/e3578266-fb63-4db8-9ab0-1ec0a0417fd6' };
  const mokaAlias = { url: `${moka.url}?utm_source=test` };
  const visited = [];
  assert.deepEqual(await captureScanJds([moka, mokaAlias], root, async url => {
    visited.push(url);
    return { url, text: 'Coding Agent responsibilities and qualifications' };
  }), { captured: 1, reused: 0, failed: 0 });
  assert.deepEqual(visited, [moka.url]);
  assert.equal(readScanJd(moka.url, root).url, moka.url);
  assert.equal(scanJdPath(moka.url, root), scanJdPath(mokaAlias.url, root));
  assert.equal(readScanJd(offer.url, root, Date.now() + JD_MAX_AGE_MS), null);
  const bad = { url: 'https://example.com/jobs/empty' };
  assert.equal((await captureScanJds([bad], root, async () => ({ text: '' }))).failed, 1);
  assert.equal(readScanJd(bad.url, root), null);
  assert.equal((await captureScanJds([bad], root, extract)).captured, 1);
  const redirected = { url: 'https://example.com/jobs/redirected' };
  assert.equal((await captureScanJds([redirected], root, async () => ({ url: 'https://example.com/', text: 'Other page' }))).failed, 1);
  assert.equal(readScanJd(redirected.url, root), null);
  const blocked = async () => { throw new Error('navigation error: HTTP 403'); };
  const jobsdb = 'https://hk.jobsdb.com/job/95358046';
  const job = { id: '95358046', title: 'AI Engineer', advertiser: { name: 'JFE Consulting Limited' },
    content: '<h2>Responsibilities</h2><p>Build agent workflows.</p><h2>Requirements</h2><p>Python experience.</p>' };
  const fetchJobsdb = async (url, options) => {
    assert.equal(url, 'https://hk.jobsdb.com/graphql');
    assert.equal(options.method, 'POST');
    assert.equal(options.redirect, 'error');
    assert.equal(JSON.parse(options.body).variables.id, '95358046');
    assert.match(JSON.parse(options.body).query, /content\(platform: WEB\)/);
    return { data: { jobDetails: { job } } };
  };
  const posting = await extractPosting(jobsdb, blocked, url => readJobsdbPosting(url, fetchJobsdb));
  assert.equal(posting.url, jobsdb);
  assert.match(posting.text, /JFE Consulting Limited/);
  assert.match(posting.text, /Build agent workflows/);
  assert.match(posting.text, /Python experience/);
  const fullContent = 'Responsibilities '.repeat(400) + 'Final requirement.';
  const longPosting = await readJobsdbPosting(jobsdb, async () => ({
    data: { jobDetails: { job: { ...job, content: fullContent } } },
  }));
  assert.equal(longPosting.text.endsWith('Final requirement.'), true);
  assert.equal(longPosting.text.includes(fullContent), true);
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => new Response(JSON.stringify(await fetchJobsdb(url, options)));
    assert.deepEqual(await extractPosting(jobsdb, blocked), posting);
  } finally { globalThis.fetch = originalFetch; }
  for (const response of [
    { errors: [{ message: 'rate limited' }] },
    { data: { jobDetails: null } },
    { data: { jobDetails: { job: { ...job, id: '95358047' } } } },
    { data: { jobDetails: { job: { ...job, content: '' } } } },
    { data: { jobDetails: { job: { ...job, advertiser: null } } } },
  ]) assert.equal(await readJobsdbPosting(jobsdb, async () => response), null);
  for (const url of ['https://evil.example/job/95358046', 'http://hk.jobsdb.com/job/95358046',
    'https://hk.jobsdb.com/jobs/95358046', 'https://hk.jobsdb.com/job/not-a-number']) {
    assert.equal(await readJobsdbPosting(url, async () => { throw new Error('must not fetch'); }), null);
  }
  await assert.rejects(extractPosting(jobsdb, blocked, async () => { throw new Error('API unavailable'); }), /HTTP 403/);
  assert.deepEqual(await extractPosting(offer.url, blocked, async url => ({ url, text: 'API description' })), { url: offer.url, text: 'API description' });
  await assert.rejects(extractPosting(offer.url, blocked, async () => null), /HTTP 403/);
  assert.equal((await extractPosting(offer.url, extract, async () => { throw new Error('unused'); })).title, 'Engineer');
  const ibm = { url: 'https://careers.ibm.com/careers/JobDetail?jobId=131606' };
  const localized = 'https://careers.ibm.com/en_US/careers/JobDetail?jobId=131606';
  assert.equal(samePostingUrl(ibm.url, localized), true);
  assert.equal(samePostingUrl(ibm.url, localized.replace('131606', '131607')), false);
  const chartered = 'https://jobs.standardchartered.com/job/Principal-AI-Engineer/59473-en_GB';
  assert.equal(samePostingUrl(chartered, `${chartered}?&feedid=363857`), true);
  assert.equal(samePostingUrl(chartered, `${chartered.replace('59473', '59474')}?&feedid=363857`), false);
  assert.equal(samePostingUrl(`${chartered}/`, chartered), true);
  assert.equal((await captureScanJds([ibm], root, async () => ({ url: localized, text: 'IBM job description' }))).captured, 1);
  assert.equal(readScanJd(ibm.url, root).url, localized);
  console.log('scan-jd: capture, dedup, reuse, expiry and failure retry passed');
} finally { rmSync(root, { recursive: true, force: true }); }

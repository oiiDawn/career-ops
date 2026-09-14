/** Verify scan handoff reuse, expiry and failed-page fallback without network access. */
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { captureScanJds, readScanJd, JD_MAX_AGE_MS } from '../lib/scan-jd.mjs';
const root = mkdtempSync(join(tmpdir(), 'scan-jd-'));
try {
  const offer = { url: 'https://example.com/jobs/123' };
  let calls = 0;
  const extract = async url => { calls++; return { url, title: 'Engineer', text: 'Responsibilities and qualifications' }; };
  assert.deepEqual(await captureScanJds([offer, offer], root, extract), { captured: 1, reused: 0, failed: 0 });
  assert.equal(readScanJd(offer.url, root).text, 'Responsibilities and qualifications');
  assert.equal((await captureScanJds([offer], root, extract)).reused, 1);
  assert.equal(calls, 1);
  assert.equal(readScanJd(offer.url, root, Date.now() + JD_MAX_AGE_MS), null);
  const bad = { url: 'https://example.com/jobs/empty' };
  assert.equal((await captureScanJds([bad], root, async () => ({ text: '' }))).failed, 1);
  assert.equal(readScanJd(bad.url, root), null);
  assert.equal((await captureScanJds([bad], root, extract)).captured, 1);
  console.log('scan-jd: capture, dedup, reuse, expiry and failure retry passed');
} finally { rmSync(root, { recursive: true, force: true }); }

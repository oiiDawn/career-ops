/** Verify that HKSTP activity is explicit, current and bound to the requested posting. */
import assert from 'node:assert/strict';
import { checkLivenessViaApi, resolveAtsApi } from '../../adapters/node/browser/liveness-api.mjs';
const url = 'https://talentjobseeker.hkstp.org/job/104358/Software-Engineer-Full-Stack-';
const valid = { id: 104358, status: 'active', publish_at: '2020-01-01T00:00:00Z', expire_at: '2099-01-01T00:00:00Z' };
assert.equal(resolveAtsApi(url).apiUrl, 'https://talentjobseeker.hkstp.org/api/position/104358');
assert.equal(resolveAtsApi(url.replace('hkstp.org', 'hkstp.org.example.com')), null);
const originalFetch = globalThis.fetch;
try {
  for (const [data, expected] of [
    [valid, 'active'], [{ ...valid, id: 104301 }, undefined],
    [{ ...valid, status: 'inactive' }, undefined], [{ ...valid, status: undefined }, undefined],
    [{ ...valid, publish_at: '2099-01-01T00:00:00Z' }, undefined],
    [{ ...valid, expire_at: '2020-01-01T00:00:00Z' }, undefined],
    [{ ...valid, expire_at: 'invalid' }, undefined], [null, undefined],
  ]) {
    globalThis.fetch = async (apiUrl, options) => {
      assert.equal(apiUrl, resolveAtsApi(url).apiUrl);
      assert.equal(options.redirect, 'error');
      return Response.json({ data });
    };
    assert.equal((await checkLivenessViaApi(url))?.result, expected);
  }
  for (const status of [403, 404, 410, 500]) {
    globalThis.fetch = async () => new Response('', { status });
    assert.equal(await checkLivenessViaApi(url), null);
  }
} finally { globalThis.fetch = originalFetch; }
console.log('HKSTP: matching active posting, publication window and inconclusive errors passed');

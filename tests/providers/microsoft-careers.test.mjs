// tests/providers/microsoft-careers.test.mjs — pure resolve/parse tests, no network.
import { pass, fail, run, ROOT } from '../helpers.mjs';
import { join } from 'path';
import { pathToFileURL } from 'url';

console.log('\nProvider — microsoft-careers');

try {
  const mod = await import(pathToFileURL(join(ROOT, 'providers/microsoft-careers.mjs')).href);
  const { parseMicrosoftResponse } = mod;
  const provider = mod.default;

  if (provider.id === 'microsoft-careers') pass('microsoft-careers.id correct');
  else fail(`microsoft-careers.id=${provider.id}`);

  // detect on a jobs.careers.microsoft.com URL resolves to PCS API
  const hit = provider.detect({ name: 'Microsoft', careers_url: 'https://jobs.careers.microsoft.com/global/en/search' });
  if (hit && hit.url.includes('/api/pcsx/search') && hit.url.includes('domain=microsoft.com')) {
    pass('microsoft-careers detect() maps jobs host to PCS API');
  } else fail(`microsoft-careers detect=${JSON.stringify(hit)}`);

  // detect rejects foreign host
  if (provider.detect({ name: 'X', careers_url: 'https://example.com/careers' }) === null) pass('microsoft-careers detect null for foreign host');
  else fail('microsoft-careers should reject foreign host');

  // parseMicrosoftResponse happy path
  const json = {
    status: 200,
    data: {
      count: 1,
      positions: [{
        name: 'Software Engineer',
        positionUrl: '/careers/job/123456',
        locations: ['Beijing', 'Shanghai'],
        postedTs: 1700000000,
      }],
    },
  };
  const jobs = parseMicrosoftResponse(json, 'Microsoft');
  if (jobs.length === 1 && jobs[0].title === 'Software Engineer'
      && jobs[0].url === 'https://apply.careers.microsoft.com/careers/job/123456'
      && jobs[0].location === 'Beijing; Shanghai' && jobs[0].postedAt === 1700000000 * 1000) {
    pass('microsoft-careers parseMicrosoftResponse normalizes a position');
  } else fail(`microsoft-careers parse=${JSON.stringify(jobs)}`);

  // parse rejects error envelope
  try {
    parseMicrosoftResponse({ status: 500 }, 'Microsoft');
    fail('microsoft-careers should throw on error envelope');
  } catch { pass('microsoft-careers throws on error envelope'); }

  // parse rejects untrusted position URL
  try {
    parseMicrosoftResponse({ status: 200, data: { count: 1, positions: [{ name: 'X', positionUrl: 'https://evil.com/job/1' }] } }, 'Microsoft');
    fail('microsoft-careers should throw on untrusted URL');
  } catch { pass('microsoft-careers throws on untrusted position URL'); }

} catch (e) {
  fail(`microsoft-careers provider tests crashed: ${e.message}`);
}
/** Verify HKSTP postings keep the API's employer, location, date and JD, and expired ones are dropped. */
import assert from 'node:assert/strict';
import hkstp, { parseHkstpPosition } from '../../../adapters/node/providers/hkstp.mjs';

const locations = new Map([[24, 'Hong Kong SAR'], [23, 'China']]);
const body = '<p><strong>About</strong> ' + 'Build agent services for startups. '.repeat(10) + '</p>';
const row = { id: '104410', slug: 'AI-Engineer', job_title: 'AI Engineer', job_description: body,
  publish_at: '2026-10-07T02:22:16.000000Z', expire_at: '2027-01-05T23:59:59.000000Z',
  company: { company_name: 'THE GRIND LIMITED' }, location_id: [24, 23] };
const now = Date.parse('2026-10-10T00:00:00Z');
const job = parseHkstpPosition(row, locations, now);
assert.equal(job.url, 'https://talentjobseeker.hkstp.org/job/104410/AI-Engineer');
assert.equal(job.company, 'THE GRIND LIMITED');
assert.equal(job.location, 'Hong Kong SAR; China');
assert.equal(job.postedAt, Date.parse('2026-10-07T02:22:16Z'));
assert.equal(job.description.startsWith('About Build agent services'), true);
assert.deepEqual([job.scan_jd.text, job.scan_jd.final_url], [job.description, job.url]);
assert.equal(parseHkstpPosition({ ...row, expire_at: '2026-10-01T00:00:00Z' }, locations, now), null);
assert.equal(parseHkstpPosition({ ...row, company: null }, locations, now), null);
assert.equal(parseHkstpPosition({ ...row, job_description: '<p>short</p>' }, locations, now).scan_jd, undefined);

const asked = [];
const jobs = await hkstp.fetch({ name: 'HKSTP' }, { fetchJson: async url => {
  asked.push(url);
  if (url.endsWith('/api/taxonomy')) return { location: [{ id: 24, name: 'Hong Kong SAR' }] };
  const page = Number(new URL(url).searchParams.get('page'));
  return { data: page === 1 ? [row] : [{ ...row, id: '2' }], meta: { last_page: 2 } };
} });
assert.equal(jobs.length, 2);
assert.equal(jobs[0].location, 'Hong Kong SAR');
assert.equal(asked.filter(url => url.includes('/api/position?')).length, 2);
assert.equal(new URL(asked[1]).searchParams.get('order'), 'publish_at');
console.log('hkstp: positions, expiry and paging passed');

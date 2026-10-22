/** Check source-scoped searches, fair limits, JD evidence, deduplication and partial failures. */
import assert from 'node:assert/strict';
import { collectSearch, jobFromPage, searchOptions, searchRequest, withinSites } from '../../../adapters/node/providers/search.mjs';

const entry = { name: 'Board', provider: 'search', search: { method: 'web', sites: ['jobs.example.com/roles'], locations: ['Hong Kong'] }, max_results: 3 };
const options = searchOptions(entry);
assert.equal(searchRequest(options, '智能体 & AI'), 'site:jobs.example.com/roles "智能体 & AI" ("Hong Kong")');
const linkedin = searchOptions({ search: { method: 'linkedin', sites: ['linkedin.com/jobs/view'], locations: ['Shanghai, China'] } });
assert.equal(new URL(searchRequest(linkedin, '智能体 & AI')).searchParams.get('keywords'), '智能体 & AI');
assert.equal(new URL(searchRequest(linkedin, 'AI', 1)).searchParams.get('start'), '25');
assert.equal(new URL(searchRequest(linkedin, 'AI')).searchParams.get('f_TPR'), 'r604800');
const xian = searchOptions({ search: { ...linkedin, locations: ["Xi'an, Shaanxi, China"], posted_within_days: 30 } });
const xianQuery = new URL(searchRequest(xian, 'Backend'));
assert.equal(xianQuery.searchParams.get('location'), "Xi'an, Shaanxi, China");
assert.equal(xianQuery.searchParams.get('f_TPR'), 'r2592000');
assert.equal(xianQuery.searchParams.has('f_C'), false);
for (const days of [0, -1, 1.5, 31, '30', true, null]) {
  assert.throws(() => searchOptions({ search: { ...linkedin, posted_within_days: days } }), /posted_within_days/);
}
for (const url of ['https://jobs.example.com.evil/roles/1', 'https://jobs.example.com/roles-other/1', 'http://jobs.example.com/roles/1', 'https://u:p@jobs.example.com/roles/1']) assert.equal(withinSites(url, options.sites), false);
assert.throws(() => searchOptions({ ...entry, search: { ...entry.search, sites: ['127.0.0.1'] } }), /Invalid/);
assert.throws(() => searchOptions({ ...entry, max_results: 0 }), /max_results/);
const detail = url => ({ url, postings: [{ '@type': 'JobPosting', title: 'AI Engineer', hiringOrganization: { name: 'Actual Employer' },
  description: 'Develop production AI applications. '.repeat(12), datePosted: '2026-09-30',
  jobLocation: { address: { addressLocality: 'Hong Kong', addressCountry: 'HK' } } }] });
const url = n => `https://jobs.example.com/roles/${n}`;
const searched = [], read = [];
const jobs = await collectSearch(entry, { searchKeywords: ['AI', '智能体'] }, {
  search: async query => { searched.push(query); return (query.includes('"AI"') ? [1, 2, 3] : [1, 4, 5]).map(n => ({ url: url(n), description: 'Not a JD' })); },
  read: async address => { read.push(address); return detail(address); },
});
assert.deepEqual(jobs.map(job => job.url), [url(1), url(4), url(2)]);
assert.equal(jobs.length, 3);
assert.equal(jobs.collectionTruncated, true);
assert.equal(jobs.collectionTruncationKind, 'result_cap');
assert.equal(jobs[0].company, 'Actual Employer');
assert.equal(jobs[0].location, 'Hong Kong, HK');
assert.equal(jobs[0].scan_jd.text, jobs[0].description);
assert.equal(searched.length, 2);
assert.equal(read.length, 3);
const efinancial = { ...entry, search: { method: 'web', sites: ['efinancialcareers.hk'], locations: ['Hong Kong'] } };
const efinancialDetail = 'https://www.efinancialcareers.hk/jobs-Hong_Kong-AI_Engineer.id123?ref=search';
const efinancialRenamed = 'https://efinancialcareers.hk/jobs-Hong_Kong-Senior_AI_Engineer.id123';
const efinancialOtherPages = [
  'https://www.efinancialcareers.hk/news/2018/09/hong-kong-machine-learning-ai-hsbc',
  'https://www.efinancialcareers.hk/jobs/artificial-intelligence/in-hong-kong',
  'https://www.efinancialcareers.hk/jobs/backend-engineering/at-tribus/in-hong-kong',
  'https://www.efinancialcareers.hk/foo/jobs-AI_Engineer.id123',
  'https://www.efinancialcareers.hk/jobs-AI_Engineer.id123/related',
];
const efinancialReads = [];
const efinancialJobs = await collectSearch(efinancial, { searchKeywords: ['AI', 'Backend'] }, {
  search: async query => (query.includes('"AI"') ? efinancialOtherPages : [efinancialDetail, efinancialRenamed]).map(url => ({ url })),
  read: async address => {
    efinancialReads.push(address);
    return { ...detail(address), postings: [{ ...detail(address).postings[0], url: efinancialRenamed }] };
  },
});
assert.deepEqual(efinancialReads, [efinancialDetail]);
assert.equal(efinancialJobs.length, 1);
assert.equal(efinancialJobs.collectionTruncated, false);
assert.throws(() => jobFromPage({ postings: [{ ...detail(efinancialDetail).postings[0],
  url: efinancialRenamed.replace('id123', 'id456') }] }, efinancialDetail), /JobPosting/);
const forbiddenDetail = n => `https://www.efinancialcareers.hk/jobs-Hong_Kong-Engineer.id${n}`;
const continuedReads = [];
const continued = await collectSearch(efinancial, { searchKeywords: ['AI', 'Backend'] }, {
  search: async query => (query.includes('"AI"') ? [1, 2] : [1, 3]).map(n => ({ url: forbiddenDetail(n) })),
  read: async address => {
    continuedReads.push(address);
    if (address === forbiddenDetail(1)) throw new Error('HTTP 403');
    return detail(address);
  },
});
assert.deepEqual(continuedReads, [forbiddenDetail(1), forbiddenDetail(3), forbiddenDetail(2)]);
assert.equal(continued.length, 2);
assert.equal(continued.collectionTruncated, true);
assert.equal(continued.collectionTruncationKind, 'incomplete_details');
assert.throws(() => jobFromPage({ postings: [] }, url(1)), /JobPosting/);
assert.throws(() => jobFromPage({ postings: [detail(url(1)).postings[0], detail(url(2)).postings[0]] }, url(1)), /JobPosting/);
assert.throws(() => jobFromPage({ postings: [{ ...detail(url(1)).postings[0], description: 'Search snippet' }] }, url(1)), /substantive/);
const chamber = jobFromPage({ text: `\nSystems Engineer II\nGo back »\nCompany:\nEmployer\nLocation:\nShanghai\nJob description\n${'Build and operate services. '.repeat(12)}\nSkills & experience\nEngineering experience.\nContact\nEmail` },
  'https://www.europeanchamber.com.cn/en/job-vacancies/5336/Systems_Engineer_II');
assert.equal(chamber.title, 'Systems Engineer II');
assert.equal(chamber.company, 'Employer');
assert.equal(chamber.location, 'Shanghai');
assert(chamber.description.includes('Engineering experience.'));
assert.throws(() => jobFromPage({ ...detail(url(1)), text: 'This job has been expired' }, url(1)), /expired/);
const partial = await collectSearch(entry, { searchKeywords: ['AI', '智能体'] }, {
  search: async query => { if (query.includes('"AI"')) throw new Error('Search unavailable'); return [{ url: url(1) }, { url: url(2) }]; },
  read: async address => address === url(1) ? { url: 'https://evil.example/job', postings: [] } : detail(address),
});
assert.equal(partial.length, 1);
assert.equal(partial.collectionTruncated, true);
assert.equal(partial.collectionTruncationKind, 'incomplete_details');
let blockedReads = 0;
const blocked = await collectSearch(entry, { searchKeywords: ['AI', '智能体'] }, {
  search: async () => [1, 2, 3].map(n => ({ url: url(n) })),
  read: async () => { blockedReads++; throw new Error('HTTP 429'); },
});
assert.equal(blockedReads, 1);
assert.equal(blocked.collectionTruncated, true);
const aliases = ['https://cn.linkedin.com/jobs/view/engineer-at-acme-123?refId=one', 'https://www.linkedin.com/jobs/view/123?refId=two'];
assert.throws(() => jobFromPage({ postings: [{ ...detail(aliases[0]).postings[0],
  url: 'https://www.linkedin.com/foo/jobs/view/123' }] }, aliases[0]), /JobPosting/);
const deduped = await collectSearch({ ...entry, search: linkedin }, { searchKeywords: ['AI', '智能体'], maxPages: 1 }, {
  search: async () => aliases.map(url => ({ url })), read: async address => detail(address),
});
assert.equal(deduped.length, 1);

const retryEntry = { ...entry, search: linkedin, max_results: 2 };
const realNow = Date.now;
const realError = console.error;
const terminalWarnings = [];
let now = realNow();
Date.now = () => now;
console.error = message => terminalWarnings.push(message);
try {
  const extendedStart = now;
  const extended = await collectSearch({ name: 'Xi’an', search: xian, max_results: 70 }, {
    searchKeywords: ['Backend'], maxPages: 1,
  }, {
    search: async () => Array.from({ length: 70 }, (_, index) => ({ url: `https://www.linkedin.com/jobs/view/${1000 + index}` })),
    read: async address => {
      now += 10_000;
      const page = detail(address);
      page.postings[0].hiringOrganization.name = Number(address.split('/').pop()) % 2 ? 'Employer A' : 'Employer B';
      return page;
    },
  });
  assert.equal(extended.length, 70, 'LinkedIn keeps collecting beyond the previous ten-minute deadline');
  assert.ok(now - extendedStart > 600_000);
  assert.deepEqual(new Set(extended.map(job => job.company)), new Set(['Employer A', 'Employer B']));
  const waits = [], attempts = new Map();
  const retryContext = { searchKeywords: ['AI', '智能体'], maxPages: 1, deadlineMs: now + 600_000,
    sleep: async ms => { waits.push(ms); now += ms; } };
  let searchAttempts = 0;
  const recovered = await collectSearch(retryEntry, retryContext, {
    search: async request => {
      if (++searchAttempts === 1) throw new Error('HTTP 429');
      return [{ url: `https://www.linkedin.com/jobs/view/${new URL(request).searchParams.get('keywords') === 'AI' ? 1 : 2}` }];
    },
    read: async address => {
      const count = (attempts.get(address) || 0) + 1;
      attempts.set(address, count);
      if (address.endsWith('/1') && count <= 2) throw new Error('HTTP 429');
      return detail(address);
    },
  });
  assert.equal(recovered.length, 2);
  assert.deepEqual(terminalWarnings, [], 'Recovered requests must not become Python collector failure warnings');
  assert.deepEqual(waits, [10_000, 10_000, 20_000], 'Retry search and detail with exponential backoff');
  assert.equal(attempts.get('https://www.linkedin.com/jobs/view/1'), 3);

  waits.length = 0;
  let exhaustedAttempts = 0;
  const exhausted = await collectSearch(retryEntry, { ...retryContext, deadlineMs: now + 600_000 }, {
    search: async request => (new URL(request).searchParams.get('keywords') === 'AI' ? [3, 7] : [4])
      .map(id => ({ url: `https://www.linkedin.com/jobs/view/${id}` })),
    read: async address => {
      if (address.endsWith('/3')) { exhaustedAttempts++; throw new Error('HTTP 429'); }
      return detail(address);
    },
  });
  assert.equal(exhaustedAttempts, 3, 'A URL has at most two retries');
  assert.deepEqual(waits, [10_000, 20_000]);
  assert.deepEqual(exhausted.map(j => j.url), ['https://www.linkedin.com/jobs/view/4', 'https://www.linkedin.com/jobs/view/7'], 'Exhaustion preserves the same queue and other keyword queues');
  assert.equal(exhausted.collectionTruncationKind, 'incomplete_details');
  assert(terminalWarnings.some(message => message.includes('jobs/view/3: HTTP 429')), 'Report terminal request failures');

  waits.length = 0;
  let deferredAttempts = 0;
  const deferred = await collectSearch(retryEntry, { ...retryContext, searchKeywords: ['AI'], deadlineMs: now + 600_000 }, {
    search: async () => [11, 12].map(id => ({ url: `https://www.linkedin.com/jobs/view/${id}` })),
    read: async address => {
      if (address.endsWith('/11')) { deferredAttempts++; throw Object.assign(new Error('HTTP 429'), { retryAfter: '120' }); }
      return detail(address);
    },
  });
  assert.equal(deferredAttempts, 1, 'Do not retry before a server delay that exceeds the local wait limit');
  assert.deepEqual(waits, []);
  assert.deepEqual(deferred.map(j => j.url), ['https://www.linkedin.com/jobs/view/12']);

  let headerAttempts = 0;
  const headerRecovered = await collectSearch(retryEntry, { ...retryContext, searchKeywords: ['AI'], deadlineMs: now + 600_000 }, {
    search: async () => [{ url: 'https://www.linkedin.com/jobs/view/13' }],
    read: async address => {
      if (++headerAttempts === 1) throw Object.assign(new Error('HTTP 429'), { retryAfter: '30' });
      return detail(address);
    },
  });
  assert.equal(headerRecovered.length, 1);
  assert.deepEqual(waits, [30_000]);

  waits.length = 0;
  let failedSearchAttempts = 0;
  const searchExhausted = await collectSearch(retryEntry, { ...retryContext, deadlineMs: now + 600_000 }, {
    search: async request => {
      if (new URL(request).searchParams.get('keywords') === 'AI') { failedSearchAttempts++; throw new Error('HTTP 429'); }
      return [{ url: 'https://www.linkedin.com/jobs/view/8' }];
    }, read: async address => detail(address),
  });
  assert.equal(failedSearchAttempts, 3);
  assert.equal(searchExhausted.length, 1, 'An exhausted search does not discard other keywords');
  assert.deepEqual(waits, [10_000, 20_000]);

  waits.length = 0;
  let budgetAttempts = 0;
  const budgeted = await collectSearch(retryEntry, { ...retryContext, deadlineMs: now + 75_000 + 5_000 }, {
    search: async () => [{ url: 'https://www.linkedin.com/jobs/view/5' }],
    read: async () => { budgetAttempts++; throw new Error('HTTP 429'); },
  });
  assert.equal(budgetAttempts, 1, 'Do not retry or start other work without enough remaining budget');
  assert.deepEqual(waits, []);
  assert.equal(budgeted.collectionTruncated, true);

  let lateAttempts = 0;
  const late = await collectSearch(retryEntry, { ...retryContext, deadlineMs: now + 75_000 + 15_000,
    sleep: async ms => { waits.push(ms); now += 20_000; } }, {
    search: async () => [{ url: 'https://www.linkedin.com/jobs/view/9' }],
    read: async () => { lateAttempts++; throw new Error('HTTP 429'); },
  });
  assert.equal(lateAttempts, 1, 'Recheck the deadline after a delayed timer wakes');
  assert.deepEqual(waits, [10_000]);
  assert.equal(late.collectionTruncated, true);

  waits.length = 0;
  let forbiddenAttempts = 0;
  const forbidden = await collectSearch(retryEntry, { ...retryContext, deadlineMs: now + 600_000 }, {
    search: async () => [{ url: 'https://www.linkedin.com/jobs/view/10' }],
    read: async () => { forbiddenAttempts++; throw new Error('HTTP 403'); },
  });
  assert.equal(forbiddenAttempts, 1, 'Do not retry authorization failures');
  assert.deepEqual(waits, []);
  assert.equal(forbidden.length, 0);
  let expiredForbiddenReads = 0;
  const expiredForbidden = await collectSearch(efinancial, {
    searchKeywords: ['AI', 'Backend'], deadlineMs: now + 75_000 + 5_000,
  }, {
    search: async () => [1, 2].map(n => ({ url: forbiddenDetail(n) })),
    read: async () => { expiredForbiddenReads++; now += 6_000; throw new Error('HTTP 403'); },
  });
  assert.equal(expiredForbiddenReads, 1, 'A 403 does not extend the collection deadline');
  assert.equal(expiredForbidden.collectionTruncated, true);
} finally { Date.now = realNow; console.error = realError; }
console.log('Scoped search collection passed');

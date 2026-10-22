/** Check LinkedIn list identity, terminal responses and pagination independently of global job deduplication. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as provider from '../../../adapters/node/providers/search.mjs';

const entry = { name: 'LinkedIn', search: { method: 'linkedin', sites: ['linkedin.com/jobs/view'],
  locations: ["Xi'an, Shaanxi, China"], posted_within_days: 30 }, max_results: 100 };
const url = id => `https://www.linkedin.com/jobs/view/${id}`;
const rows = ids => ids.map(id => ({ url: url(id) }));
const read = async address => ({ url: address, postings: [{ title: 'AI Engineer',
  hiringOrganization: { name: 'Employer' }, description: 'Build production agent applications. '.repeat(10) }] });
const request = (word = 'AI', page = 0) => provider.searchRequest(provider.searchOptions(entry), word, page);

test('LinkedIn uses the public listing endpoint with continuous ten-record offsets', () => {
  const second = new URL(request('Backend', 1));
  assert.equal(second.pathname, '/jobs-guest/jobs/api/seeMoreJobPostings/search');
  assert.equal(second.searchParams.get('start'), '10');
  assert.equal(second.searchParams.get('location'), "Xi'an, Shaanxi, China");
  assert.equal(second.searchParams.get('f_TPR'), 'r2592000');
  assert.equal(second.searchParams.has('f_C'), false);
});

test('only a verified blank response or explicit empty state ends a LinkedIn list', () => {
  const raw = { url: request(), anchors: [], text: '' };
  for (const body of ['', '\n', '<!DOCTYPE html>\n\n<!---->  ']) {
    assert.deepEqual(provider.linkedInSearchRows({ ...raw, body }, request()), []);
  }
  assert.deepEqual(provider.linkedInSearchRows({ ...raw, text: 'No matching jobs' }, request()), []);
  for (const text of ['', 'Sign in to LinkedIn', 'Security verification required']) {
    assert.throws(() => provider.linkedInSearchRows({ ...raw, text }, request()), /no readable results/);
  }
  for (const body of ['<script>showChallenge()</script>', '<html><body></body></html>']) {
    assert.throws(() => provider.linkedInSearchRows({ ...raw, body }, request()), /no readable results/);
  }
  const reordered = new URL(request());
  reordered.searchParams.sort();
  assert.equal(provider.linkedInSearchRows({ ...raw, url: reordered.href,
    anchors: [{ href: url(1) }, { href: 'https://example.com/job/2' }] }, request()).length, 1);
});

test('LinkedIn rejects redirects that reset the offset or alter the query', () => {
  const requested = request('AI', 1);
  for (const changed of [request('AI', 0), request('Backend', 1),
    requested.replace('/jobs-guest/jobs/api/seeMoreJobPostings/search', '/jobs/search/'),
    requested.replace('www.linkedin.com', 'evil.example'), `${requested}&f_C=123`]) {
    assert.throws(() => provider.linkedInSearchRows({ url: changed, anchors: [], text: '', body: '' },
      requested), /redirected/);
  }
});

test('a page already collected by another keyword does not hide later jobs', async () => {
  const jobs = await provider.collectSearch(entry, { searchKeywords: ['AI', 'Backend'] }, {
    search: async address => {
      const query = new URL(address).searchParams;
      const page = Number(query.get('start')) / 10;
      return rows(query.get('keywords') === 'AI' ? [[1], [2], [3], []][page] : [[2], []][page]);
    }, read,
  });
  assert.deepEqual(jobs.map(job => job.url), [url(1), url(2), url(3)]);
  assert.equal(jobs.collectionTruncated, false);
});

test('overlapping pages continue but the same keyword repeating an ID set stops', async () => {
  const overlap = await provider.collectSearch(entry, { searchKeywords: ['AI'] }, {
    search: async address => rows([[1, 2], [2, 3], []][Number(new URL(address).searchParams.get('start')) / 10]), read,
  });
  assert.deepEqual(overlap.map(job => job.url), [url(1), url(2), url(3)]);
  assert.equal(overlap.collectionTruncated, false);
  let calls = 0;
  const repeated = await provider.collectSearch(entry, { searchKeywords: ['AI'] }, {
    search: async () => ++calls === 1 ? rows([1, 2]) : [
      { url: 'https://cn.linkedin.com/jobs/view/engineer-at-employer-2?refId=next' },
      { url: 'https://cn.linkedin.com/jobs/view/engineer-at-employer-1?refId=next' },
    ], read,
  });
  assert.equal(calls, 2);
  assert.equal(repeated.length, 2);
  assert.equal(repeated.collectionTruncated, true);
});

test('the converted page limit permits more than ten pages and preserves probe caps', async () => {
  const search = async address => {
    const offset = Number(new URL(address).searchParams.get('start'));
    return offset < 110 ? rows([offset + 1]) : [];
  };
  const jobs = await provider.collectSearch(entry, { searchKeywords: ['AI'] }, { search, read });
  assert.equal(jobs.length, 11);
  assert.equal(jobs.collectionTruncated, false);
  const full = await provider.collectSearch(entry, { searchKeywords: ['AI'] }, {
    search: async address => rows([Number(new URL(address).searchParams.get('start')) + 1]), read,
  });
  assert.equal(full.length, 25);
  assert.equal(full.collectionQueries.length, 25);
  assert.equal(full.collectionTruncated, true);
  const capped = await provider.collectSearch(entry, { searchKeywords: ['AI'], maxPages: 1 }, { search, read });
  assert.equal(capped.length, 1);
  assert.equal(capped.collectionTruncated, true);
  const empty = await provider.collectSearch(entry, { searchKeywords: ['AI'], maxPages: 1 }, {
    search: async () => [], read,
  });
  assert.equal(empty.collectionTruncated, false);
});

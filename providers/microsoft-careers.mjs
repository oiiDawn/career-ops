// Microsoft public PCS search JSON. Legacy careers hosts now route to apply.
// Verified without cookies/tokens: /api/pcsx/search?domain=microsoft.com.
// The old gcsservices endpoint fails TLS; /api/apply/v2/jobs returns 403.
// PCS returns 10 rows even when num=100; paginate by the actual response size.

import { sleep } from './_http.mjs';

const ORIGIN = 'https://apply.careers.microsoft.com';
const HOSTS = new Set(['jobs.careers.microsoft.com', 'careers.microsoft.com', 'apply.careers.microsoft.com']);
const API = `${ORIGIN}/api/pcsx/search?domain=microsoft.com`;

/** Pin both auto-detected legacy pages and explicit API configuration. */
function resolveApi(entry) {
  try {
    const url = new URL(entry?.api ?? entry?.careers_url);
    if (url.protocol !== 'https:' || url.username || url.password || url.port || !HOSTS.has(url.hostname)) return null;
    if (entry.api && (url.origin !== ORIGIN || url.pathname !== '/api/pcsx/search'
        || [...url.searchParams].some(([key, value]) => key !== 'domain' || value !== 'microsoft.com'))) return null;
    return API;
  } catch {
    return null;
  }
}

/** Reject error envelopes and malformed jobs instead of reporting an empty board. */
export function parseMicrosoftResponse(json, company) {
  if (json?.status !== 200 || !Array.isArray(json.data?.positions)
      || !Number.isInteger(json.data.count) || json.data.count < 0) {
    throw new Error('microsoft-careers: invalid search response');
  }
  return json.data.positions.map(row => {
    if (typeof row?.name !== 'string' || !row.name.trim() || typeof row.positionUrl !== 'string') {
      throw new Error('microsoft-careers: malformed position');
    }
    const url = new URL(row.positionUrl, ORIGIN);
    if (url.origin !== ORIGIN || url.username || url.password || !/^\/careers\/job\/\d+$/.test(url.pathname)) {
      throw new Error('microsoft-careers: untrusted position URL');
    }
    const job = { title: row.name.trim(), url: url.href, company,
      location: [...new Set((row.locations || []).filter(loc => typeof loc === 'string'))].join('; ') };
    if (typeof row.postedTs === 'number' && Number.isFinite(row.postedTs)
        && row.postedTs > 0 && row.postedTs * 1000 <= 8.64e15) job.postedAt = row.postedTs * 1000;
    return job;
  });
}

export default {
  id: 'microsoft-careers',
  detect(entry) {
    const url = resolveApi(entry);
    return url ? { url } : null;
  },
  async fetch(entry, ctx) {
    const api = resolveApi(entry);
    if (!api) throw new Error('microsoft-careers: unsupported or untrusted URL');
    const maxPages = Number.isInteger(ctx.maxPages) && ctx.maxPages > 0 ? Math.min(ctx.maxPages, 500) : 500;
    const jobs = [];
    const seen = new Set();
    let start = 0;
    for (let page = 0; page < maxPages; page++) {
      if (page) await sleep(250, ctx);
      const json = await ctx.fetchJson(`${api}&start=${start}&num=10`, { redirect: 'error' });
      const rows = parseMicrosoftResponse(json, entry.name);
      const fresh = rows.filter(row => !seen.has(row.url));
      for (const row of fresh) { seen.add(row.url); jobs.push(row); }
      start += rows.length;
      if (start >= json.data.count) return jobs;
      if (!fresh.length) throw new Error('microsoft-careers: pagination stopped before count');
    }
    console.error(`⚠️  microsoft-careers: ${entry.name} truncated at ${maxPages} pages (${jobs.length} jobs)`);
    return jobs;
  },
};

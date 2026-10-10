// @ts-check
/** @typedef {import('./_types.js').Provider} Provider */

// HKSTP Talent Pool provider — talentjobseeker.hkstp.org, the Hong Kong Science
// and Technology Parks job board for its park companies (mostly startups).
// Public JSON behind the site's own origin, no auth:
//
//   GET /api/taxonomy                                   → { location: [{ id, name }], … }
//   GET /api/position?order=publish_at&per_page=100&page=N
//   → { data: [{ id, slug, job_title, job_description (HTML), publish_at, expire_at,
//       company: { company_name }, location_id: [ids] }], meta: { last_page } }
//
// The board is small (489 postings on 2026-10-10) and every row carries the full
// JD, so the provider walks the whole inventory and hands the JD on as scan_jd.
//
//   - name: HKSTP Talent Pool
//     provider: hkstp
//     enabled: true

import { htmlToText } from './_html-to-text.mjs';

const ORIGIN = 'https://talentjobseeker.hkstp.org';
const PAGE_SIZE = 100;
// Safety bound only — the loop stops at meta.last_page (5 pages when written).
const MAX_PAGES = 30;
const PAGE_DELAY_MS = 200;

/**
 * @param {any} row
 * @param {Map<number, string>} locations
 * @param {number} [now]
 */
export function parseHkstpPosition(row, locations, now = Date.now()) {
  const title = String(row?.job_title || '').trim();
  const company = String(row?.company?.company_name || '').trim();
  const id = String(row?.id || '').trim();
  if (!title || !company || !/^\d+$/.test(id)) return null;
  if (Date.parse(row.expire_at) < now) return null;
  const url = `${ORIGIN}/job/${id}/${encodeURIComponent(String(row.slug || ''))}`;
  const description = htmlToText(String(row.job_description || '')).trim();
  const postedAt = Date.parse(row.publish_at);
  const location = (Array.isArray(row.location_id) ? row.location_id : [])
    .map(key => locations.get(Number(key))).filter(Boolean).join('; ');
  return {
    title, url, company, location,
    ...(Number.isFinite(postedAt) ? { postedAt } : {}),
    ...(description ? { description } : {}),
    ...(description.length >= 200
      ? { scan_jd: { text: description, final_url: url, retrieved_at: new Date().toISOString() } } : {}),
  };
}

/** @type {Provider} */
export default {
  id: 'hkstp',

  detect(entry) {
    try {
      return new URL(entry.careers_url || '').origin === ORIGIN ? { url: `${ORIGIN}/api/position` } : null;
    } catch { return null; }
  },

  async fetch(entry, ctx) {
    const taxonomy = /** @type {any} */ (await ctx.fetchJson(`${ORIGIN}/api/taxonomy`, { redirect: 'error' }));
    const locations = new Map((taxonomy?.location ?? []).map(item => [Number(item.id), String(item.name)]));
    const jobs = [];
    for (let page = 1; page <= MAX_PAGES; page++) {
      const url = `${ORIGIN}/api/position?order=publish_at&per_page=${PAGE_SIZE}&page=${page}`;
      let json;
      try {
        json = /** @type {any} */ (await ctx.fetchJson(url, { redirect: 'error' }));
      } catch (error) {
        if (page === 1) throw error;
        console.error(`⚠️  hkstp: ${entry.name} page ${page} fetch failed — ${error.message} (returning ${jobs.length} jobs fetched so far)`);
        break;
      }
      const rows = Array.isArray(json?.data) ? json.data : [];
      for (const row of rows) {
        const job = parseHkstpPosition(row, locations);
        if (job) jobs.push(job);
      }
      if (!rows.length || page >= Number(json?.meta?.last_page || 0)) break;
      await new Promise(resolve => setTimeout(resolve, PAGE_DELAY_MS));
    }
    return jobs;
  },
};

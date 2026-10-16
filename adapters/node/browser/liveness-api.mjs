// @ts-check
/**
 * liveness-api.mjs — zero-token liveness check for ATS-hosted job postings.
 *
 * Many postings live on ATS platforms (Greenhouse, Lever, Ashby, Workday, ...) that
 * expose a public JSON endpoint. We can confirm whether a posting is still live by
 * hitting that endpoint directly — no browser, no LLM tokens — and only fall back to
 * the Playwright check (liveness-browser.mjs) for non-ATS pages or when the API is
 * inconclusive. This is the cheap first rung of the liveness ladder.
 *
 * CONSERVATIVE BY DESIGN: a false "expired" is worse than the status quo (the user
 * misses a real job). So on a definitive 404/410 we return `expired`, and for
 * anything ambiguous (unknown ATS, redirect, 429/5xx, network/timeout) we return
 * `null` (→ caller falls back to Playwright).
 *
 * Three endpoint shapes:
 *   - Per-job (Greenhouse, Lever, Workday): the URL maps to a single-job endpoint,
 *     so a 200 is itself proof the posting is live.
 *   - Org-level (Ashby): the URL maps to the org's whole job board. A 200 only
 *     proves the board exists, so the provider's `interpret` step parses the board
 *     and confirms THIS posting is still listed before returning active/expired.
 *     (Ashby pages are JS-rendered, so the browser/static rung sees only nav/footer
 *     and false-reports live postings as expired — this API rung is authoritative.)
 *   - Per-job HTML (LinkedIn): the guest endpoint returns the rendered posting as
 *     HTML and answers 200 for closed postings too, so `interpret` reads two
 *     independent signals out of the body and only concludes when they agree.
 *
 * SSRF-safe by construction: the request URL is built from a FIXED, hard-coded API
 * host plus path segments extracted from the posting URL with a strict charset
 * (no slashes / traversal), and server-side redirects are refused.
 */

import { DEFAULT_USER_AGENT } from '../shared/user-agent.mjs';
import { resolveTenant } from '../providers/eightfold.mjs';
import { linkedInJobId } from '../shared/url-key.mjs';

const TIMEOUT_MS = 8_000;

/** Resolve a public Eightfold posting to its identity-bound SuccessFactors application page. */
export async function resolveEightfoldApplication(url) {
  const tenant = resolveTenant({ careers_url: url });
  if (!tenant) return null;
  const posting = new URL(url);
  const id = posting.pathname.match(/^\/careers\/job\/(\d+)\/?$/)?.[1];
  if (!id) return null;
  const endpoint = new URL(`https://${tenant.host}/api/apply/v2/jobs/${id}`);
  if (tenant.domain) endpoint.searchParams.set('domain', tenant.domain);
  try {
    const response = await fetch(endpoint.href, { redirect: 'error', signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { 'user-agent': DEFAULT_USER_AGENT, accept: 'application/json' } });
    if (response.status !== 200) return null;
    const data = await response.json();
    if (String(data?.id) !== id || !/^\d+$/.test(String(data.ats_job_id))) return null;
    const target = new URL(data.apply_redirect_url);
    if (target.origin !== 'https://career2.successfactors.eu' || target.pathname !== '/careers'
        || target.searchParams.get('career_ns') !== 'job_application'
        || target.searchParams.get('career_job_req_id') !== String(data.ats_job_id)
        || !target.searchParams.get('company') || target.username || target.password) return null;
    return { url: target.href, jobId: String(data.ats_job_id) };
  } catch {
    return null;
  }
}
// Strict path-segment charset. Anything with a slash, dot-dot, or other char is
// rejected before it can reach the fixed-host API URL template.
const SAFE_SEGMENT = /^[A-Za-z0-9._-]+$/;

// Most providers extract single path segments (SAFE_SEGMENT covers those directly).
// Workday's job path is genuinely multi-segment (a location slug + a title slug,
// e.g. "Toronto-ON-CAN/Agentic-AI-Engineer_R260010125"), so a `parts` value may
// itself contain slashes. This still validates every individual segment against
// the same strict charset (and rejects ".." in any of them) — it only relaxes
// "no slash at all" to "no *unsafe* content between slashes", so the traversal/
// injection guarantee is unchanged.
function isSafeValue(v) {
  if (typeof v !== 'string' || v.length === 0) return false;
  // SAFE_SEGMENT's charset includes "." (some real segments use dots), so ".."
  // alone passes that regex — same as the single-segment guard in
  // resolveAtsApi below, the explicit `!includes('..')` check per segment is
  // load-bearing, not redundant with the regex test.
  return v.split('/').every((seg) => seg.length > 0 && SAFE_SEGMENT.test(seg) && !seg.includes('..'));
}

// Each ATS: detect its posting URL, then map to a public JSON API URL.
// `match` returns the extracted path params (or null); `api` builds the FIXED-host URL.
// Optional per-provider fields:
//   `timeoutMs`  — override the default fetch timeout (slow/rate-limited APIs).
//   `throttleMs` — minimum interval between our requests to this provider.
//   `accept`     — override the Accept header (providers that answer in HTML).
//   `interpret`  — read the 200 response body to decide liveness (org-level APIs
//                  where a 200 alone doesn't prove THIS posting is live, and
//                  per-job APIs that answer 200 for a closed posting).
//   `api404Authoritative` — defaults to true (a 404/410 means gone). Set to
//                  false when the provider's public API can 404 a posting that
//                  is still genuinely live elsewhere (see the `lever` entry).
const ATS_PROVIDERS = [
  {
    id: 'hkstp',
    match(u) {
      if (u.hostname !== 'talentjobseeker.hkstp.org') return null;
      const match = u.pathname.match(/^\/job\/(\d+)\/[^/]+\/?$/);
      return match ? { id: match[1] } : null;
    },
    api: ({ id }) => `https://talentjobseeker.hkstp.org/api/position/${id}`,
    api404Authoritative: false,
    async interpret(res, { id }) {
      const { data } = await res.json();
      const now = Date.now();
      if (String(data?.id) !== id || data.status !== 'active'
          || !(Date.parse(data.publish_at) <= now && now < Date.parse(data.expire_at))) return null;
      return { result: 'active', code: 'hkstp_api_active',
        reason: 'The matching HKSTP posting is active within its publication period' };
    },
  },
  {
    id: 'smartrecruiters',
    match(u) {
      if (u.hostname !== 'jobs.smartrecruiters.com') return null;
      const match = u.pathname.match(/^\/([^/]+)\/(\d+)(?:-[^/]*)?\/?$/);
      return match ? { company: match[1], id: match[2] } : null;
    },
    api: ({ company, id }) => `https://api.smartrecruiters.com/v1/companies/${company}/postings/${id}`,
    api404Authoritative: false,
    async interpret(res, { company, id }) {
      const posting = await res.json();
      if (String(posting?.id) !== id || posting.active !== true || posting.visibility !== 'PUBLIC') return null;
      const apply = new URL(posting.applyUrl);
      if (apply.protocol !== 'https:' || apply.hostname !== 'jobs.smartrecruiters.com'
          || !apply.pathname.startsWith(`/${company}/${id}-`)) return null;
      return { result: 'active', code: 'smartrecruiters_api_active',
        reason: 'The matching public posting is active and provides an application URL' };
    },
  },
  {
    id: 'greenhouse',
    // boards.greenhouse.io/{board}/jobs/{id} · job-boards[.eu].greenhouse.io/{board}/jobs/{id}
    match(u) {
      if (!/(^|\.)greenhouse\.io$/.test(u.hostname)) return null;
      const m = u.pathname.match(/^\/([^/]+)\/jobs\/(\d+)\/?$/);
      return m ? { board: m[1], id: m[2] } : null;
    },
    api: ({ board, id }) => `https://boards-api.greenhouse.io/v1/boards/${board}/jobs/${id}`,
  },
  {
    id: 'lever',
    // jobs.(eu.)?lever.co/{slug}/{id}
    match(u) {
      const host = u.hostname.match(/^jobs\.((?:eu\.)?lever\.co)$/);
      if (!host) return null;
      const m = u.pathname.match(/^\/([^/]+)\/([^/?#]+)\/?$/);
      return m ? { apiHost: `api.${host[1]}`, slug: m[1], id: m[2] } : null;
    },
    api: ({ apiHost, slug, id }) => `https://${apiHost}/v0/postings/${slug}/${id}`,
    // Lever's Confidential/Internal Postings feature explicitly excludes some
    // live postings from the public v0/postings API while the direct
    // jobs.lever.co page keeps serving them normally. Real-world repro
    // (2026-08-09): api.lever.co 404s two postings whose jobs.lever.co pages
    // return 200 with the real job title and a working Apply control. A 404
    // here is NOT proof of removal — fall through to Playwright instead.
    api404Authoritative: false,
  },
  {
    id: 'ashby',
    // jobs.ashbyhq.com/{org}/{jobId}[/application]. Ashby's public posting API is
    // ORG-level (the whole job board), not per-job — so `api` maps to the board and
    // `interpret` confirms this {jobId} is still listed. Only {org} reaches the
    // fixed-host URL; {jobId} is used solely to filter the parsed board (SAFE_SEGMENT
    // still validates both).
    match(u) {
      if (u.hostname !== 'jobs.ashbyhq.com') return null;
      const m = u.pathname.match(/^\/([^/]+)\/([^/]+)(?:\/application)?\/?$/);
      return m ? { org: m[1], jobId: m[2] } : null;
    },
    api: ({ org }) => `https://api.ashbyhq.com/posting-api/job-board/${org}`,
    // Ashby's posting-api has a server-side latency floor and rate-limits repeated
    // unauthenticated hits (see providers/ashby.mjs). Give it more room than the ATS
    // default so a slow-but-live board doesn't time out into a Playwright fallback.
    timeoutMs: 20_000,
    async interpret(res, { jobId }) {
      let json;
      try {
        json = await res.json();
      } catch {
        return null; // unparseable body → inconclusive, let the browser decide
      }
      return classifyAshbyBoard(json, jobId);
    },
  },
  {
    id: 'workday',
    // {tenant}.{shard}.myworkdayjobs.com[/{xx-XX}]/{site}/job/{jobPath...}
    // Mirrors the tenant/shard/site detection in providers/workday.mjs, but for a
    // single posting rather than the board-wide CXS search endpoint. Workday's
    // per-job CXS endpoint (`/wday/cxs/{tenant}/{site}/job/{jobPath}`) is a
    // genuinely PER-JOB API like Greenhouse/Lever — a 200 is itself proof the
    // posting is live, confirmed against real tenants (BMO, TD, Manulife, CIBC):
    // an existing posting returns 200, a garbage job id returns 404.
    //
    // jobPath is intentionally multi-segment (Workday encodes a location slug and
    // a title slug as separate path parts, e.g.
    // "Toronto-ON-CAN/Agentic-AI-Engineer_R260010125") — isSafeValue (not the
    // single-segment SAFE_SEGMENT check other providers use directly) validates
    // it component-by-component.
    match(u) {
      const m = `${u.hostname}${u.pathname}`.match(
        /^([\w-]+)\.(wd[\w-]*)\.myworkdayjobs\.com\/(?:[a-z]{2}-[A-Z]{2}\/)?([^/?#]+)\/job\/(.+?)\/?$/
      );
      if (!m) return null;
      const [, tenant, shard, site, jobPath] = m;
      return { tenant, shard, site, jobPath };
    },
    api: ({ tenant, shard, site, jobPath }) =>
      `https://${tenant}.${shard}.myworkdayjobs.com/wday/cxs/${tenant}/${site}/job/${jobPath}`,
  },
  {
    id: 'linkedin',
    // linkedin.com/jobs/view/{id} · .../jobs/view/{title-slug}-{id} · any page that
    // carries the posting in ?currentJobId= (search and collection views).
    //
    // Guest HTML returns 200 for both live and closed postings. Missing signals
    // require the rendered detail page; conflicting signals remain uncertain.
    match(u) {
      const id = linkedInJobId(u.href);
      return id ? { id } : null;
    },
    api: ({ id }) => `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/${id}`,
    // The endpoint is unauthenticated and rate-limited. Space our calls; the
    // interval sits on the provider so it holds for every caller rather than only
    // one particular liveness collection loop.
    throttleMs: 3_500,
    // We parse HTML here, so ask for it. The endpoint also serves HTML under an
    // application/json Accept, but a request that misdescribes what it wants is one
    // content-negotiation change away from breaking silently.
    accept: 'text/html',
    async interpret(res) {
      let html;
      try {
        html = await res.text();
      } catch {
        return null; // unreadable body → inconclusive, let the browser decide
      }
      return classifyLinkedInPosting(html);
    },
  },
];

// LinkedIn renders a closed posting with an explicit banner
// (`<figcaption class="closed-job__flavor--closed">No longer accepting
// applications</figcaption>`) and drops the apply control. A live posting shows one
// of two apply controls: the on-site button, or the off-site sign-in modal.
const LINKEDIN_CLOSED_MARKER = /(?:No longer|Not currently) accepting applications|已停止接受求职申请|不再接受應徵/i;
const LINKEDIN_APPLY_CONTROL = /public_jobs_apply-link-onsite|job-details-topcard-apply-modal/;

/**
 * Decide liveness for one LinkedIn posting from its guest-endpoint HTML.
 * Pure + deterministic (no I/O), mirroring classifyLiveness in liveness-core.mjs.
 *
 * The two signals are read independently and must agree before this concludes
 * anything. A body carrying the closed banner AND an apply control, or neither, is
 * a page we do not recognise — a layout change, a partial render, an interstitial —
 * and it returns `uncertain` rather than picking the likelier answer.
 *
 * The asymmetry is deliberate and is the whole reason for the two-signal rule, and
 * it is this module's CONSERVATIVE BY DESIGN rule applied to a body read rather than
 * a status code: a wrong `expired` costs the user a real job they never see again,
 * while a wrong `uncertain` costs one re-check on the next sweep.
 *
 * @param {any} html - the guest endpoint's response body
 * @returns {{ result: 'active' | 'expired' | 'uncertain', code: string, reason: string } | null}
 *   null = nothing to read (empty or non-string body) → caller falls back.
 */
export function classifyLinkedInPosting(html) {
  if (typeof html !== 'string' || html.length === 0) return null;
  const closed = html.match(LINKEDIN_CLOSED_MARKER);
  const apply = LINKEDIN_APPLY_CONTROL.test(html);
  if (closed && !apply) {
    return {
      result: 'expired',
      code: 'linkedin_closed_marker',
      evidence: { excerpt: closed[0] },
      reason: 'LinkedIn shows "No longer accepting applications" and no apply control',
    };
  }
  if (apply && !closed) {
    return {
      result: 'active',
      code: 'linkedin_apply_control',
      reason: 'LinkedIn shows an apply control and no closure banner (live)',
    };
  }
  return {
    result: 'uncertain',
    code: closed ? 'linkedin_signals_disagree' : 'linkedin_signals_missing',
    reason: closed
      ? 'LinkedIn shows both a closure banner and an apply control — unrecognised page'
      : 'LinkedIn shows neither a closure banner nor an apply control — unrecognised page',
  };
}

// Reserved send times per provider, so back-to-back callers queue behind each
// other instead of all reading the same "last request" timestamp and firing
// together.
const nextRequestAt = new Map();

/**
 * Wait until this provider's next request slot, then reserve the one after it.
 *
 * @param {string} providerId
 * @param {number} [intervalMs] - minimum spacing; falsy means no throttling
 * @returns {Promise<number>} milliseconds actually waited
 */
export async function throttleProviderRequest(providerId, intervalMs) {
  if (!intervalMs) return 0;
  const now = Date.now();
  const earliest = Math.max(now, nextRequestAt.get(providerId) ?? 0);
  nextRequestAt.set(providerId, earliest + intervalMs);
  const wait = earliest - now;
  if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
  return wait;
}

/**
 * Decide liveness for one Ashby posting from its org's job-board API payload.
 * Pure + deterministic (no I/O), mirroring classifyLiveness in liveness-core.mjs.
 *
 * The public board lists only currently-published postings, so a posting that is
 * absent (or explicitly `isListed: false`) has been removed/unlisted → expired.
 * A present, listed posting → active. An unexpected shape → null (inconclusive),
 * so a future API change degrades to a Playwright fallback rather than a false
 * "expired".
 *
 * @param {any} json - parsed job-board response, expected shape `{ jobs: [...] }`
 * @param {string} jobId - the {jobId} from jobs.ashbyhq.com/{org}/{jobId}
 * @returns {{ result: 'active' | 'expired', code: string, reason: string } | null}
 */
export function classifyAshbyBoard(json, jobId) {
  if (!json || !Array.isArray(json.jobs)) return null; // unexpected shape → fall back
  const target = String(jobId).toLowerCase();
  const job = json.jobs.find((j) => typeof j?.id === 'string' && j.id.toLowerCase() === target);
  if (job && job.isListed !== false) {
    return { result: 'active', code: 'ashby_api_ok', reason: 'Ashby posting is listed on the board (live)' };
  }
  return { result: 'expired', code: 'ashby_api_unlisted', reason: 'Ashby posting not listed on the board — removed/unlisted' };
}

/**
 * Map a posting URL to its ATS API URL, or null if it isn't a known ATS posting
 * (or any extracted segment fails the strict charset). Pure + deterministic.
 * @param {string} rawUrl
 * @returns {{ ats: string, apiUrl: string, parts: Record<string, string>, timeoutMs?: number, throttleMs?: number, accept?: string, interpret?: (res: Response, parts: Record<string, string>) => Promise<{ result: 'active' | 'expired' | 'uncertain', code: string, reason: string } | null>, api404Authoritative: boolean } | null}
 */
export function resolveAtsApi(rawUrl) {
  let u;
  try {
    u = new URL(rawUrl);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:') return null;
  for (const provider of ATS_PROVIDERS) {
    const parts = provider.match(u);
    if (!parts) continue;
    // SSRF guard: every derived value must be safe — a single path segment for
    // most providers, or (Workday) a slash-separated sequence of safe segments.
    // isSafeValue enforces the same charset + no-".." rule either way.
    if (!Object.values(parts).every(isSafeValue)) return null;
    return {
      ats: provider.id,
      apiUrl: provider.api(parts),
      parts,
      timeoutMs: provider.timeoutMs,
      throttleMs: provider.throttleMs,
      accept: provider.accept,
      interpret: provider.interpret,
      api404Authoritative: provider.api404Authoritative !== false,
    };
  }
  return null;
}

/** True if `url` is an ATS posting we can check via API (lets callers stay lazy about the browser). */
export function isAtsPosting(url) {
  return resolveAtsApi(url) !== null;
}

/**
 * Zero-token liveness check via the posting's ATS API.
 * @param {string} url
 * @returns {Promise<{ result: 'active' | 'expired' | 'uncertain', code: string, reason: string } | null>}
 *   null = not a known ATS posting, or inconclusive → caller should fall back to Playwright.
 *   LinkedIn missing signals require a rendered-page check; conflicting signals
 *   remain uncertain instead of choosing one over the other.
 */
export async function checkLivenessViaApi(url) {
  const resolved = resolveAtsApi(url);
  if (!resolved) return null;
  const { ats, apiUrl, parts, interpret, timeoutMs, throttleMs, accept, api404Authoritative } = resolved;

  // Wait out any provider rate limit BEFORE arming the timeout, so the spacing
  // does not eat the budget the request itself needs.
  await throttleProviderRequest(ats, throttleMs);

  // The timeout guards the whole classification (fetch + any `interpret` body read),
  // since aborting the shared signal also tears down an in-flight res.json().
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs || TIMEOUT_MS);
  try {
    let res;
    try {
      res = await fetch(apiUrl, {
        method: 'GET',
        headers: { 'user-agent': DEFAULT_USER_AGENT, accept: accept || 'application/json' },
        redirect: 'error', // refuse server-side redirects (SSRF + ambiguity guard)
        signal: controller.signal,
      });
    } catch {
      return null; // network / timeout / redirect → inconclusive, let Playwright decide
    }

    if (res.status === 404 || res.status === 410) {
      if (!api404Authoritative) return null; // inconclusive → let Playwright check the real page
      return { result: 'expired', code: `${ats}_api_gone`, reason: `ATS API ${res.status} — posting removed`,
        evidence: { source_url: apiUrl, posting_url: url, status: res.status, provider: ats } };
    }
    if (res.status === 200) {
      // Org-level APIs (Ashby) inspect the body to confirm THIS posting; per-job
      // APIs (Greenhouse, Lever) treat a 200 as proof the posting is live.
      if (interpret) {
        const verdict = await interpret(res, parts);
        return verdict && { ...verdict, evidence: { ...verdict.evidence, source_url: apiUrl, posting_url: url, status: res.status, provider: ats } };
      }
      return { result: 'active', code: `${ats}_api_ok`, reason: 'ATS API returns the posting (live)',
        evidence: { source_url: apiUrl, posting_url: url, status: res.status, provider: ats } };
    }
    return null; // 429/5xx/other → inconclusive, fall back to the browser check
  } catch {
    return null; // interpret abort / unexpected error → inconclusive
  } finally {
    clearTimeout(timer);
  }
}

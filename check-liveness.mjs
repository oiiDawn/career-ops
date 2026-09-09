#!/usr/bin/env node

/**
 * check-liveness.mjs — Playwright job link liveness checker
 *
 * Tests whether job posting URLs are still active or have expired.
 * 只读检查；默认覆盖机会库中的 Pending 和 Scored。
 * Zero Claude API tokens. Two rungs: a free public-API check first
 * (liveness-api.mjs, no browser), then Playwright for everything else.
 *
 * Usage:
 *   node check-liveness.mjs                    # Pending + Scored
 *   node check-liveness.mjs <url1> [url2] ...
 *   node check-liveness.mjs --file urls.txt
 *
 * Exit code: 0 if all active, 1 if any expired or uncertain
 */

import { chromium } from 'playwright';
import { readFile } from 'fs/promises';
import { pathToFileURL } from 'url';
import {
  checkUrlLivenessWithFallback,
  createHeadedPageProvider,
  newLivenessPage,
  jitteredDelayMs,
  sleep,
} from './liveness-browser.mjs';
import { checkLivenessViaApi } from './liveness-api.mjs';

/** 从机会库提取待处理和已评分条目的岗位 URL；保留顺序并去重。 */
export function collectPipelineUrls(text) {
  const urls = new Set();
  let eligible = false;
  for (const line of text.split(/\r?\n/)) {
    if (/^##\s+/.test(line)) {
      eligible = /^##\s+(?:Pending\b|Pendientes\b|Scored\b|Awaiting Confirmation\b|待处理|已评分)/i.test(line);
      continue;
    }
    if (!eligible || !/^\s*- \[[ !~]\]\s+/.test(line)) continue;
    const cells = line.replace(/^\s*- \[[ !~]\]\s+/, '').split('|').map(cell => cell.trim());
    const posting = cells[0].startsWith('#') ? cells[1] : cells[0];
    const url = posting?.match(/^https?:\/\/[^\s]+/)?.[0];
    if (url) urls.add(url);
  }
  return [...urls];
}

/** 显式 URL/文件优先；无参数时读取 canonical 机会库，不写入状态。 */
export async function loadLivenessUrls(positional) {
  if (positional.length === 0) {
    const file = process.env.CAREER_OPS_PIPELINE || new URL('./data/pipeline.md', import.meta.url);
    return collectPipelineUrls(await readFile(file, 'utf-8'));
  }
  if (positional[0] === '--file') {
    if (positional.length !== 2) throw new Error('--file 需要一个 URL 列表文件');
    const text = await readFile(positional[1], 'utf-8');
    return text.split('\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
  }
  if (positional.some(arg => arg.startsWith('-'))) throw new Error('未知参数：请使用 URL 或 --file <文件>');
  return positional;
}

async function main() {
  const args = process.argv.slice(2);

  // Portals like pracuj.pl serve a Cloudflare anti-bot wall to headless Chromium.
  // On a challenge we retry once in a headed browser (which clears it); pass
  // --no-fallback to stay fully headless (e.g. on a machine with no display).
  const noFallback = args.includes('--no-fallback');
  // --throttle or --throttle=<ms>: wait base..2*base ms (jittered) between checks
  // to stay under rate-based WAF limits. pracuj.pl's Cloudflare flags the session
  // after ~2 rapid hits, so a bulk run needs spacing. Default base 5000ms.
  const throttleArg = args.find((a) => a === '--throttle' || a.startsWith('--throttle='));
  const throttleBaseMs = throttleArg ? (Number(throttleArg.split('=')[1]) || 5000) : 0;
  const positional = args.filter((a) => a !== '--no-fallback' && a !== throttleArg);

  const urls = await loadLivenessUrls(positional);

  const notes = [
    noFallback ? null : 'headed fallback on challenge',
    throttleBaseMs ? `throttle ~${throttleBaseMs / 1000}-${(throttleBaseMs * 2) / 1000}s` : null,
  ].filter(Boolean);
  console.log(`Checking ${urls.length} URL(s)...${notes.length ? ` (${notes.join(', ')})` : ''}\n`);

  // Lazy browser: the API rung resolves ATS postings with no browser at all, so we
  // only launch Playwright if a URL actually needs the fallback.
  let browser = null, page = null, headed = null;
  async function ensureBrowser() {
    if (browser) return;
    browser = await chromium.launch({ headless: true });
    page = await newLivenessPage(browser);
    headed = noFallback ? null : createHeadedPageProvider(chromium);
  }

  let active = 0, expired = 0, uncertain = 0, viaApi = 0;

  // Sequential — project rule: never Playwright in parallel
  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    let result, reason, usedBrowser = false;

    // Rung 1: zero-token ATS API check. A conclusive active/expired wins; otherwise fall through.
    const api = await checkLivenessViaApi(url);
    if (api) {
      ({ result, reason } = api);
      viaApi++;
    } else {
      // Rung 2: Playwright — handles non-ATS pages and inconclusive API results.
      await ensureBrowser();
      const getHeadedPage = headed ? () => headed.get() : undefined;
      ({ result, reason } = await checkUrlLivenessWithFallback(page, url, { getHeadedPage }));
      usedBrowser = true;
    }

    const icon = { active: '✅', expired: '❌', uncertain: '⚠️' }[result];
    console.log(`${icon} ${result.padEnd(10)} ${api ? '(api) ' : '      '}${url}`);
    if (result !== 'active') console.log(`           ${reason}`);
    if (result === 'active') active++;
    else if (result === 'expired') expired++;
    else uncertain++;

    // Throttle only matters between browser checks (the API is cheap, not WAF-rate-limited).
    const wait = usedBrowser && i < urls.length - 1 ? jitteredDelayMs(throttleBaseMs) : 0;
    if (wait) await sleep(wait);
  }

  if (headed) await headed.close();
  if (browser) await browser.close();

  console.log(`\nResults: ${active} active  ${expired} expired  ${uncertain} uncertain  (${viaApi} via API, no browser)`);
  if (expired > 0 || uncertain > 0) process.exit(1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(err => {
    console.error('Fatal:', err.message);
    process.exit(1);
  });
}

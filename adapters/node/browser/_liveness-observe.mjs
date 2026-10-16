/** Stream independent ATS/browser observations; a failed URL cannot erase prior results. */

import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { checkLivenessViaApi } from './liveness-api.mjs';
import {
  checkUrlLivenessWithFallback, createHeadedPageProvider, newLivenessPage,
  jitteredDelayMs, sleep,
} from './liveness-browser.mjs';

const [inputPath] = process.argv.slice(2);
if (!inputPath) throw new Error('input JSON path is required');
const { urls, headed_fallback: headedFallback, throttle_ms: throttleMs } =
  JSON.parse(await readFile(inputPath, 'utf8'));
if (!Array.isArray(urls) || urls.some(url => typeof url !== 'string')) {
  throw new Error('urls must be a string array');
}

let browser, page, headed;
try {
  for (let index = 0; index < urls.length; index++) {
    const url = urls[index];
    let observation, api;
    try {
      api = await checkLivenessViaApi(url);
      observation = api;
      if (!api || api.code === 'linkedin_signals_missing') {
        api = null;
        if (!browser?.isConnected()) {
          browser = await chromium.launch({ headless: true });
          page = null;
        }
        if (!page || page.isClosed()) page = await newLivenessPage(browser);
        if (headedFallback && !headed) headed = createHeadedPageProvider(chromium);
        observation = await checkUrlLivenessWithFallback(page, url, {
          getHeadedPage: headed ? () => headed.get() : undefined,
        });
      }
    } catch (error) {
      observation = { result: 'uncertain', code: 'collection_error', reason: String(error).slice(0, 500) };
      if (page) await page.close().catch(() => {});
      page = null;
    }
    process.stdout.write(JSON.stringify({ ...observation, url, checked_at: new Date().toISOString(),
      via_api: Boolean(api), evidence: observation.evidence || {} }) + '\n');
    if (!api && index < urls.length - 1 && throttleMs > 0) await sleep(jitteredDelayMs(throttleMs));
  }
} finally {
  if (headed) await headed.close().catch(() => {});
  if (browser) await browser.close().catch(() => {});
}

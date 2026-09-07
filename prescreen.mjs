#!/usr/bin/env node
/** CLI adapter for the canonical Stage 0 contract and cache. */

import { readFileSync } from 'fs';
import { resolve } from 'path';
import { fileURLToPath } from 'url';
import { evaluatePrescreen, isReusablePrescreen } from './lib/prescreen-core.mjs';
import { readPrescreenCache, writePrescreenCache } from './lib/prescreen-cache.mjs';

const usage = 'Usage: node prescreen.mjs --input evidence.json [--cache-dir data/prescreen-cache]';

export function runPrescreen(input, { cacheDir } = {}) {
  const url = input?.job?.url;
  if (!url) throw new Error('input.job.url is required');
  const cached = cacheDir ? readPrescreenCache(url, cacheDir) : null;
  if (cached && isReusablePrescreen(cached.result, input)) return { ...cached.result, cache: 'reused' };
  const result = evaluatePrescreen(input);
  if (cacheDir) writePrescreenCache(url, input, result, cacheDir);
  return { ...result, cache: cached ? 'refreshed' : 'written' };
}

async function main() {
  const args = process.argv.slice(2);
  const value = (flag) => { const index = args.indexOf(flag); return index === -1 ? null : args[index + 1]; };
  const inputPath = value('--input');
  if (!inputPath || args.some((arg) => arg.startsWith('--') && !['--input', '--cache-dir'].includes(arg))) throw new Error(usage);
  const input = JSON.parse(readFileSync(inputPath, 'utf8'));
  console.log(JSON.stringify(runPrescreen(input, { cacheDir: value('--cache-dir') }), null, 2));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch((error) => {
    console.error(`prescreen: ${error.message}`);
    process.exitCode = 1;
  });
}


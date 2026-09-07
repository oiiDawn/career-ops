/** Filesystem boundary for application-independent Stage 0 cache records. */

import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { hashValue, validatePrescreenResult } from './prescreen-core.mjs';

export function prescreenCachePath(url, root = 'data/prescreen-cache') {
  return join(resolve(root), `${hashValue(String(url)).slice(0, 24)}.json`);
}

export function readPrescreenCache(url, root) {
  try {
    const record = JSON.parse(readFileSync(prescreenCachePath(url, root), 'utf8'));
    return validatePrescreenResult(record.result).valid ? record : null;
  } catch {
    return null;
  }
}

export function writePrescreenCache(url, input, result, root) {
  const validation = validatePrescreenResult(result);
  if (!validation.valid) throw new Error(`invalid prescreen result: ${validation.errors.join(', ')}`);
  const target = prescreenCachePath(url, root);
  mkdirSync(dirname(target), { recursive: true });
  const temporary = `${target}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify({ url, input, result }, null, 2)}\n`);
  renameSync(temporary, target);
  return target;
}


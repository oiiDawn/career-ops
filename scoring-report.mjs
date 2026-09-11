#!/usr/bin/env node
/** Recompute and validate evidence-backed attractiveness pilot reports without publishing them. */
import { readFileSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { load } from 'js-yaml';

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIMENSIONS = ['direction', 'compensation', 'team', 'company'];
export const HEADINGS = [
  'Machine Summary', 'A. 岗位概览', 'B. 能力竞争力', 'C. 入职吸引力',
  'D. 薪酬与需求', 'E. CV 变更计划', 'F. 面试与补证', 'G. 岗位真实性',
  'Risk Summary', 'Evaluation Checklist',
];

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function exactKeys(value, keys, label) {
  requireValue(value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(','), `${label}: unexpected or missing keys`);
}

/** Unknown dimensions contribute their full [1, 5] range and no evidence coverage. */
export function calculateAttractiveness(dimensions, weights) {
  exactKeys(weights, DIMENSIONS, 'weights');
  exactKeys(dimensions, DIMENSIONS, 'dimensions');
  requireValue(Object.values(weights).every(w => Number.isFinite(w) && w > 0)
    && Math.abs(Object.values(weights).reduce((a, b) => a + b, 0) - 1) < 1e-9, 'weights must be positive and sum to 1');
  let lower = 0, upper = 0, coverage = 0;
  for (const key of DIMENSIONS) {
    const score = dimensions[key]?.score;
    requireValue(score === null || (Number.isInteger(score) && score >= 1 && score <= 5), `${key}: score must be null or an integer from 1 to 5`);
    lower += weights[key] * (score ?? 1);
    upper += weights[key] * (score ?? 5);
    if (score !== null) coverage += weights[key];
  }
  return { lower: Number(lower.toFixed(2)), upper: Number(upper.toFixed(2)), coverage: Number(coverage.toFixed(6)) };
}

export function scoreLabel({ lower, upper, coverage }) {
  return `**入职吸引力：** ${lower.toFixed(2)}–${upper.toFixed(2)}/5；证据覆盖率：${Number((coverage * 100).toFixed(4))}%`;
}

/** Validate structure, frozen sources, literal citations and arithmetic; semantic review remains required. */
export function validateReport(text, { root = ROOT } = {}) {
  const headings = [...text.matchAll(/^## (.+)$/gm)];
  requireValue(headings.map(m => m[1]).join('|') === HEADINGS.join('|'), 'report headings must match the pilot contract in order');
  for (let i = 0; i < headings.length; i++) {
    const body = text.slice(headings[i].index + headings[i][0].length, headings[i + 1]?.index ?? text.length).trim();
    requireValue(body.length >= 20, `empty section: ${headings[i][1]}`);
  }
  const fence = text.match(/## Machine Summary\s*\n+```(?:yaml|yml)\s*\n([\s\S]*?)\n```/);
  requireValue(fence, 'missing Machine Summary YAML');
  const summary = load(fence[1]);
  requireValue(summary?.scoring_model === 'attractiveness-v1' && summary.scope === 'pilot', 'not an attractiveness-v1 pilot');
  requireValue(summary.score === null, 'pilot must not publish a legacy scalar score');
  requireValue(summary.complete_jd === true, 'complete JD required; record incomplete without a scored report');
  requireValue(typeof summary.company === 'string' && summary.company.trim()
    && typeof summary.role === 'string' && summary.role.trim(), 'company and role required');
  requireValue(Array.isArray(summary.sources) && summary.sources.length > 0, 'sources required');
  const sources = new Map();
  const base = realpathSync(root);
  for (const source of summary.sources) {
    requireValue(typeof source.id === 'string' && source.id.trim() && !sources.has(source.id), 'source IDs must be unique');
    requireValue(typeof source.path === 'string' && !isAbsolute(source.path), 'source path must be repository-relative');
    const path = realpathSync(resolve(base, source.path));
    const rel = relative(base, path);
    requireValue(rel !== '..' && !rel.startsWith('../') && !isAbsolute(rel), 'source escapes repository');
    const bytes = readFileSync(path);
    requireValue(createHash('sha256').update(bytes).digest('hex') === source.sha256, `source hash mismatch: ${source.id}`);
    sources.set(source.id, bytes.toString('utf8'));
  }
  requireValue(typeof summary.jd_source === 'string' && sources.has(summary.jd_source), 'jd_source must reference frozen JD');
  requireValue(sources.has('profile'), 'frozen profile required');
  requireValue(sources.has('cv') && sources.has('rules'), 'frozen candidate CV and scoring rules required');
  const profile = load(sources.get('profile'));
  requireValue(profile?.attractiveness?.model === summary.scoring_model, 'profile model mismatch');
  const result = calculateAttractiveness(summary.dimensions, profile.attractiveness.weights);
  for (const key of DIMENSIONS) {
    const dimension = summary.dimensions[key];
    exactKeys(dimension, ['score', 'rationale', 'evidence'], key);
    requireValue(typeof dimension.rationale === 'string' && dimension.rationale.trim().length > 0, `${key}: rationale required`);
    requireValue(Array.isArray(dimension.evidence), `${key}: evidence must be an array`);
    requireValue(dimension.score === null || dimension.evidence.length > 0, `${key}: known score requires evidence`);
    for (const citation of dimension.evidence) {
      requireValue(typeof citation?.quote === 'string' && citation.quote.trim().length > 0
        && sources.get(citation.source)?.includes(citation.quote), `${key}: quote not found in cited frozen source`);
    }
  }
  exactKeys(summary.attractiveness, ['lower', 'upper', 'coverage'], 'attractiveness');
  for (const key of Object.keys(result)) {
    requireValue(summary.attractiveness[key] === result[key], `${key}: expected ${result[key]}`);
  }
  const body = text.slice(headings[1].index);
  requireValue(body.includes(scoreLabel(result)), 'body score/range does not match Machine Summary');
  const scoreSection = text.slice(headings[3].index, headings[4].index);
  for (const key of DIMENSIONS) {
    requireValue(scoreSection.includes(`| ${key} | ${summary.dimensions[key].score ?? 'Unknown'} |`), `${key}: missing or inconsistent body score row`);
  }
  return { company: summary.company, role: summary.role, ...result };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const paths = process.argv.slice(2);
  if (!paths.length) {
    console.error('Usage: node scoring-report.mjs <pilot-report.md>...');
    process.exitCode = 1;
  }
  for (const path of paths) {
    try {
      console.log(JSON.stringify({ path, valid: true, ...validateReport(readFileSync(path, 'utf8')) }));
    } catch (error) {
      console.log(JSON.stringify({ path, valid: false, error: error.message }));
      process.exitCode = 1;
    }
  }
}

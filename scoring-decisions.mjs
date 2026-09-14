#!/usr/bin/env node
/** Build the current shortlist from reviewed reports and deterministic action rules. */
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { load } from 'js-yaml';
import { GATES, validateReviewedReport } from './scoring-report.mjs';

const ORDER = ['apply', 'deprioritize', 'discard'];
const ROOT = dirname(fileURLToPath(import.meta.url));

/** Read only Scored rows; historical scores require reassessment and invalid reports fail closed. */
export function readShortlist(pipeline, { root = ROOT, profile } = {}) {
  const decisions = [], needs_review = [], invalid = [];
  const section = pipeline.match(/^## Scored[^\n]*\n([\s\S]*?)(?=^## |$(?![\s\S]))/m)?.[1] ?? '';
  for (const line of section.split('\n').filter(line => /^- \[~\]/.test(line))) {
    const id = line.match(/#(\d+)/)?.[1];
    const report = line.match(/Report:\s*([^|\n]+\.md)/)?.[1]?.trim();
    const item = { id, report, row: line };
    try {
      if (!id || !report) throw new Error('report number and path required');
      const path = resolve(root, report);
      if (!path.startsWith(resolve(root, 'reports') + '/')) throw new Error('report must be inside reports');
      const text = readFileSync(path, 'utf8');
      const summary = load(text.match(/## Machine Summary\s*\n+```(?:yaml|yml)\s*\n([\s\S]*?)\n```/)?.[1] ?? '');
      if (summary?.scoring_model !== 'attractiveness-v1') {
        needs_review.push({ ...item, reason: '历史评分待重评' });
        continue;
      }
      const review = JSON.parse(readFileSync(`${path}.review.json`, 'utf8'));
      const score = validateReviewedReport(text, review, { root });
      if (score.scoring_model !== profile?.attractiveness?.model
        || Object.keys(score.weights).some(key => score.weights[key] !== profile.attractiveness.weights?.[key])) throw new Error('report scoring policy differs from current profile');
      classifyOpportunity(score, review.gates, profile.attractiveness.alert_line);
      decisions.push({ ...item, score, gates: review.gates, ready: review.ready, deadline: null, effort_days: null });
    } catch (error) { invalid.push({ ...item, error: error.message }); }
  }
  return { decisions: orderOpportunities(decisions, profile.attractiveness.alert_line), needs_review, invalid };
}

/** Hard failures cannot be compensated by the coverage-adjusted attractiveness score. */
export function classifyOpportunity(score, gates, alertLine) {
  if (!Number.isFinite(alertLine) || alertLine < 1 || alertLine > 5) throw new Error('explicit alert line from 1 to 5 required');
  if (!score || !Number.isFinite(score.lower) || !Number.isFinite(score.upper)
    || score.lower < 1 || score.upper > 5 || score.lower > score.upper
    || !Number.isFinite(score.coverage) || score.coverage < 0 || score.coverage > 1) throw new Error('invalid score range');
  if (!gates || Object.keys(gates).sort().join(',') !== [...GATES].sort().join(',')
    || Object.values(gates).some(s => !['Pass', 'Fail', 'Unknown'].includes(s))) throw new Error('complete gate states required');
  if (Object.values(gates).includes('Fail')) return 'discard';
  const combined = score.lower + (score.upper - score.lower) * score.coverage;
  return combined >= alertLine ? 'apply' : 'deprioritize';
}

/** Order actions by explicit deadline, effort and evidence, retaining stable IDs for ties. */
export function orderOpportunities(items, alertLine) {
  const ids = new Set();
  const rows = items.map(item => {
    if (typeof item.id !== 'string' || !item.id.trim() || ids.has(item.id)) throw new Error('unique opportunity IDs required');
    ids.add(item.id);
    if (item.deadline !== null && (typeof item.deadline !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(item.deadline)
      || !Number.isFinite(Date.parse(item.deadline)) || new Date(item.deadline).toISOString().slice(0, 10) !== item.deadline)) throw new Error('deadline must be ISO date or null');
    if (item.effort_days !== null && (!Number.isFinite(item.effort_days) || item.effort_days < 0)) throw new Error('effort_days must be nonnegative or null');
    return { ...item, action: classifyOpportunity(item.score, item.gates, alertLine) };
  });
  return rows.sort((a, b) => ORDER.indexOf(a.action) - ORDER.indexOf(b.action)
    || (a.deadline ?? '9999-12-31').localeCompare(b.deadline ?? '9999-12-31')
    || (a.effort_days ?? Infinity) - (b.effort_days ?? Infinity)
    || b.score.coverage - a.score.coverage
    || (a.action === 'apply' ? b.score.lower - a.score.lower : 0)
    || a.id.localeCompare(b.id));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (!process.argv[2]) {
      const profile = load(readFileSync(resolve(ROOT, 'config/profile.yml'), 'utf8'));
      console.log(JSON.stringify(readShortlist(readFileSync(resolve(ROOT, 'data/pipeline.md'), 'utf8'), { profile }), null, 2));
      process.exit(0);
    }
    const input = resolve(process.argv[2]);
    const queue = JSON.parse(readFileSync(input, 'utf8'));
    const profile = load(readFileSync(resolve(dirname(input), queue.profile), 'utf8'));
    const rows = queue.opportunities.map(item => {
      const reportPath = resolve(dirname(input), item.report);
      const report = readFileSync(reportPath, 'utf8');
      const review = JSON.parse(readFileSync(`${reportPath}.review.json`, 'utf8'));
      const score = validateReviewedReport(report, review);
      if (score.scoring_model !== profile.attractiveness.model
        || Object.keys(score.weights).some(key => score.weights[key] !== profile.attractiveness.weights?.[key])) throw new Error('mixed scoring policies cannot share a ranked queue');
      if (GATES.some(key => item.gates?.[key] !== review.gates?.[key]) || item.ready !== review.ready) throw new Error('queue gates/readiness differ from semantic review');
      return { ...item, score };
    });
    console.log(JSON.stringify(orderOpportunities(rows, profile.attractiveness.alert_line), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

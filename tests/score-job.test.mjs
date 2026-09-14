/** Exercise resumable selection, deterministic reports and concurrent-safe publication. */
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { dump } from 'js-yaml';
import { prepare, selectJob, renderReport, publish, appendPending, hash } from '../score-job.mjs';
import { validateReviewedReport } from '../scoring-report.mjs';

const root = mkdtempSync(join(tmpdir(), 'score-job-'));
try {
  for (const d of ['data', 'modes', 'config']) mkdirSync(join(root, d));
  writeFileSync(join(root, 'modes/_custom.md'), '### Scoring Rules — attractiveness-v1\nCurrent rules\n### Review and decision gate\nIndependent review\n### Scoring Rules — research-required-v1\nResearch required\n');
  writeFileSync(join(root, 'modes/_profile.md'), 'Primary targeting evidence.');
  writeFileSync(join(root, 'cv.md'), 'Primary candidate evidence.');
  writeFileSync(join(root, 'config/profile.yml'), dump({ attractiveness: { model: 'attractiveness-v1', weights: { direction: .4, compensation: .3, team: .2, company: .1 }, alert_line: 4 } }));
  const pipeline = join(root, 'data/pipeline.md');
  writeFileSync(pipeline, '## Pending\n- [ ] https://example.com/a | Hangzhou | note: keep this\n- [ ] https://example.com/b\n\n## Scored\n');
  const first = await prepare(root);
  assert.equal(first.url, 'https://example.com/a');
  const second = await prepare(root);
  assert.equal(second.url, 'https://example.com/b');
  const retry = await prepare(root);
  assert.equal(retry.url, first.url);
  assert.equal(retry.attempt, 2);
  assert.equal((await prepare(root, first.url)).attempt, 3);
  assert.equal(selectJob([{ key: 'a' }, { key: 'b' }], { a: { attempts: 2 }, b: { attempts: 2 } }), undefined);
  const evidence = { company: 'Example', role: 'Engineer', complete_jd: true, liveness: 'active', jd: 'Build and maintain software products. Full responsibilities and requirements.' };
  const assessment = {
    sources: [{ id: 'web1', text: 'Primary market research excerpt.' }],
    research: { searched_at: '2026-09-11', queries: ['pay', 'team', 'company'],
      dimensions: Object.fromEntries(['compensation', 'team', 'company'].map((k, i) => [k, { queries: [i], conclusion: 'Applicable evidence remains unavailable.', next_step: 'Confirm exact employer terms.' }])),
      findings: [{ id: 'f1', url: 'https://example.com/pay', entity: 'Example', scope: 'market', status: 'retrieved', published_at: null, limitation: 'Market only, not an offer.', source: 'web1', quote: 'Primary market research excerpt.' }] },
    dimensions: Object.fromEntries(['direction', 'compensation', 'team', 'company'].map(k => [k, { score: null, rationale: 'Insufficient applicable evidence.', evidence: [] }])),
    sections: Object.fromEntries(['overview', 'capabilities', 'compensation', 'questions', 'legitimacy', 'risks', 'checklist'].map(k => [k, 'Complete evidence mapping, unknowns and specific next actions.'])),
  };
  const wrapped = structuredClone(assessment);
  wrapped.dimensions.direction.evidence = [{ source: 'jd', quote: 'build and maintain software products.' }];
  const wrappedReport = renderReport(retry, { ...evidence, jd: evidence.jd.replace('maintain ', 'maintain\n') }, wrapped);
  assert(wrappedReport.report.includes('maintain\n'));
  wrapped.dimensions.direction.evidence[0].quote = 'Build and invent software products.';
  assert.throws(() => renderReport(retry, evidence, wrapped), /quote not found/);
  const rendered = renderReport(retry, evidence, assessment);
  assert(!rendered.report.includes('CV 变更计划'));
  assert(rendered.report.includes('report_format: scoring-v2'));
  const review = { reviewer: 'independent-test', report_sha256: hash(rendered.report), verdict: 'approve', ready: false,
    gates: Object.fromEntries(['location', 'employment', 'size', 'compensation', 'eligibility', 'liveness'].map(k => [k, k === 'liveness' ? 'Pass' : 'Unknown'])),
    checks: Object.fromEntries(['jd_complete', 'source_grounding', 'dimension_support', 'capability_coverage', 'no_double_count', 'gate_evidence'].map(k => [k, { status: 'pass', finding: 'Reviewed original evidence and applicability.' }])) };
  assert.equal(validateReviewedReport(rendered.report, review, { root }).coverage, 0);
  writeFileSync(join(retry.directory, 'report.md.review.json'), JSON.stringify(review));
  assert.equal((await appendPending('- [ ] https://example.com/new-from-scan\n- [ ] https://example.com/b', root)).added, 1);
  const published = await publish(retry);
  assert.equal(published.status, 'published');
  assert.equal(published.action, 'deprioritize');
  const final = readFileSync(pipeline, 'utf8');
  assert(final.includes('https://example.com/new-from-scan'));
  assert(final.includes('- [ ] https://example.com/b'));
  assert.equal(final.match(/https:\/\/example.com\/a/g).length, 1);
  assert(final.includes('吸引力 1.00–5.00/5'));
  assert(final.includes('Hangzhou | note: keep this'));
  assert(published.report.includes(hash(rendered.report).slice(0, 12)));
  const invalid = structuredClone(assessment);
  invalid.sources[0].id = 'profile';
  assert.throws(() => renderReport(second, evidence, invalid), /sequential/);
  writeFileSync(join(root, 'cv.md'), 'Changed candidate facts.');
  await assert.rejects(() => publish(second), /changed/);
} finally { rmSync(root, { recursive: true, force: true }); }
console.log('score-job: selection, retry cap, report integrity, concurrent scan preservation and source invalidation passed');

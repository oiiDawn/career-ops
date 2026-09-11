/** Exercise scoring arithmetic and reject malformed, unsupported or inconsistent pilot reports. */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { dump } from 'js-yaml';
import { calculateAttractiveness, HEADINGS, scoreLabel, validateReport } from '../scoring-report.mjs';

const weights = { direction: 0.35, compensation: 0.3, team: 0.25, company: 0.1 };
const dimensions = Object.fromEntries(Object.keys(weights).map(key => [key, {
  score: key === 'compensation' ? null : 4,
  rationale: 'Explicit evidence or an explanation of missing information.',
  evidence: key === 'compensation' ? [] : [{ source: 'jd', quote: 'Concrete job evidence.' }],
}]));
assert.deepEqual(calculateAttractiveness(dimensions, weights), { lower: 3.1, upper: 4.3, coverage: 0.7 });
const unknown = Object.fromEntries(Object.keys(weights).map(key => [key, { score: null }]));
assert.deepEqual(calculateAttractiveness(unknown, weights), { lower: 1, upper: 5, coverage: 0 });
assert.deepEqual(calculateAttractiveness(Object.fromEntries(Object.keys(weights).map(key => [key, { score: 5 }])), weights), { lower: 5, upper: 5, coverage: 1 });
for (const score of [undefined, '4', 0, 5.5, NaN, Infinity]) {
  assert.throws(() => calculateAttractiveness({ ...dimensions, team: { score } }, weights));
}
assert.throws(() => calculateAttractiveness(dimensions, { ...weights, team: 0.5 }));
assert.throws(() => calculateAttractiveness({ ...dimensions, legitimacy: { score: 5 } }, weights));

const root = mkdtempSync(join(tmpdir(), 'scoring-report-'));
try {
  const files = {
    'profile.yml': dump({ attractiveness: { model: 'attractiveness-v1', weights } }),
    'jd.md': 'Concrete job evidence. Full responsibilities and qualifications are manually verified.',
    'cv.md': 'Approved candidate evidence for independent semantic review.',
    'rules.md': 'Frozen scoring contract used for this assessment.',
  };
  for (const [path, text] of Object.entries(files)) writeFileSync(join(root, path), text);
  const summary = {
    company: 'Sample', role: 'Engineer', scoring_model: 'attractiveness-v1', scope: 'pilot', score: null,
    complete_jd: true, jd_source: 'jd', dimensions,
    sources: Object.entries(files).map(([path, text]) => ({
      id: path.split('.')[0], path, sha256: createHash('sha256').update(text).digest('hex'),
    })),
    attractiveness: calculateAttractiveness(dimensions, weights),
  };
  const render = value => HEADINGS.map(heading => `## ${heading}\n\n${heading === 'Machine Summary'
    ? `\`\`\`yaml\n${dump(value)}\`\`\``
    : heading === 'C. 入职吸引力'
      ? `${scoreLabel(value.attractiveness)}\n\n${Object.entries(value.dimensions).map(([key, d]) => `| ${key} | ${d.score ?? 'Unknown'} | evidence |`).join('\n')}`
      : 'Manually reviewed content, evidence, limitations and next action.'}`).join('\n\n');
  const text = render(summary);
  assert.equal(validateReport(text, { root }).coverage, 0.7);
  for (const mutate of [
    s => { s.attractiveness.lower = 3.2; },
    s => { s.score = 4; },
    s => { s.complete_jd = false; },
    s => { s.jd_source = 'missing'; },
    s => { s.dimensions.team.evidence = []; },
    s => { s.dimensions.team.evidence[0].quote = 'Fabricated claim'; },
    s => { s.dimensions.compensation.rationale = ''; },
    s => { s.sources[0].sha256 = '0'.repeat(64); },
    s => { s.sources.push(s.sources[0]); },
  ]) {
    const value = structuredClone(summary);
    mutate(value);
    assert.throws(() => validateReport(render(value), { root }));
  }
  assert.throws(() => validateReport(text.replace('## Risk Summary', '## Other'), { root }));
  assert.throws(() => validateReport(text.replace('3.10–4.30/5', '4.00–4.30/5'), { root }));
  assert.throws(() => validateReport(text.replace('| team | 4 |', '| team | 5 |'), { root }));
  writeFileSync(join(root, 'jd.md'), readFileSync(join(root, 'jd.md'), 'utf8') + ' changed');
  assert.throws(() => validateReport(text, { root }), /hash mismatch/);
} finally {
  rmSync(root, { recursive: true, force: true });
}
console.log('scoring-report: arithmetic, evidence integrity and malformed-report checks passed');

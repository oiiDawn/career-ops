/** Focused tests for source-grounded single-role preparation plans. */

import { buildPreparationPlan, parseReportClassifications, validatePreparationPlan } from '../preparation-plan.mjs';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const jd = '# Role\n\n## Requirements\n- Python, Kubernetes, Rust\n';
const cv = '# Skills\nPython\n\n# Experience\nDeployed Kubernetes services.\n';
const report = '| Requirement | Match | Evidence |\n|---|---|---|\n| Rust | Adjacent | Systems work, scope unverified |\n| Security clearance | Unverified | Recruiter question |';
const plan = buildPreparationPlan({ company: 'Acme', role: 'Engineer', jdText: jd, cvText: cv, reportText: report, generatedAt: '2026-01-01T00:00:00.000Z' });

const byRequirement = Object.fromEntries(plan.requirements.map((entry) => [entry.requirement, entry.classification]));
if (byRequirement.Python !== 'evidenced') throw new Error('named CV skill must be evidenced');
if (byRequirement.Kubernetes !== 'evidence_gap') throw new Error('CV prose-only skill must be an evidence gap');
if (byRequirement.Rust !== 'adjacent') throw new Error('report classification must preserve adjacent');
if (byRequirement['Security clearance'] !== 'unverified') throw new Error('report unverified mapping must be preserved');
if (!validatePreparationPlan(plan).valid || !plan.pre_application.length || !plan.interview_preparation.length) throw new Error('plan schema and sections must validate');
if (parseReportClassifications(report).length !== 2) throw new Error('report capability rows must parse');

const root = mkdtempSync(join(tmpdir(), 'career-ops-preparation-plan-'));
try {
  writeFileSync(join(root, 'cv.md'), cv);
  writeFileSync(join(root, 'jd.md'), jd);
  const output = join(root, 'output', 'plan.json');
  const run = spawnSync(process.execPath, [
    fileURLToPath(new URL('../preparation-plan.mjs', import.meta.url)),
    '--jd', 'jd.md', '--company', 'Acme', '--role', 'Engineer', '--output', output,
  ], { cwd: root, encoding: 'utf8' });
  if (run.status !== 0 || !existsSync(output) || JSON.parse(readFileSync(output, 'utf8')).schema !== 'career-ops/preparation-plan') {
    throw new Error(`preparation-plan CLI failed: ${run.stderr}`);
  }
} finally {
  rmSync(root, { recursive: true, force: true });
}

console.log('preparation-plan: ok');

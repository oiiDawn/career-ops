/** Focused contract tests for canonical Stage 0 outcomes and cache reuse. */

import { evaluatePrescreen, isReusablePrescreen, validatePrescreenResult } from '../lib/prescreen-core.mjs';

const base = () => ({
  job: { url: 'https://example.com/jobs/1' },
  complete_jd: true,
  assessment_complete: true,
  gates: Object.fromEntries(['location', 'employment', 'compensation', 'company_size'].map((name) => [name, { status: 'pass', evidence: name }])),
  years: { required: 5, verified: 5, evidence: 'CV' },
  core_capabilities: [],
  credentials: [],
});

const pass = evaluatePrescreen(base(), { generatedAt: '2026-01-01T00:00:00.000Z' });
if (pass.status !== 'pass' || !validatePrescreenResult(pass).valid || !isReusablePrescreen(pass, base())) throw new Error('pass result must validate and reuse');

const unknown = base();
unknown.gates.compensation = { status: 'unknown', reason: 'Recruiter must confirm fixed base' };
if (evaluatePrescreen(unknown).status !== 'uncertain') throw new Error('unknown must not fail');

const incomplete = base();
incomplete.complete_jd = false;
if (evaluatePrescreen(incomplete).status !== 'incomplete') throw new Error('missing full JD must be incomplete');

const years = base();
years.years.verified = 2;
if (evaluatePrescreen(years).discard_reasons[0]?.code !== 'years_gap_terminal') throw new Error('three-year experience gap must fail audibly');

const capabilities = base();
capabilities.core_capabilities = ['Agents', 'Evaluation'].map((name) => ({ name, core: true, mandatory: true, match: 'gap' }));
if (evaluatePrescreen(capabilities).discard_reasons[0]?.code !== 'multiple_core_capability_gaps') throw new Error('two core gaps must fail');

const credential = base();
credential.credentials = [{ name: 'CPA', mandatory: true, status: 'absent', evidence: 'JD/CV' }];
if (evaluatePrescreen(credential).discard_reasons[0]?.code !== 'mandatory_credential_absent') throw new Error('missing mandatory credential must fail');

const changed = base();
changed.job.url = 'https://example.com/jobs/2';
if (isReusablePrescreen(pass, changed)) throw new Error('changed input must invalidate cache');

console.log('prescreen-core: ok');

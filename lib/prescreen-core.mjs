/** Canonical, pure Stage 0 pre-screen contract shared by scan, pipeline, and batch. */

import { createHash } from 'crypto';

export const PRESCREEN_SCHEMA = 'career-ops/prescreen';
export const PRESCREEN_SCHEMA_VERSION = 1;
export const PRESCREEN_RULES_VERSION = 2;
export const PRESCREEN_STATUSES = Object.freeze(['pass', 'fail', 'uncertain', 'incomplete']);

const HARD_GATES = ['location', 'employment', 'compensation', 'company_size'];
const GATE_STATES = new Set(['pass', 'fail', 'unknown']);

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
}

export function hashValue(value) {
  return createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');
}

export function createPrescreenMetadata(input, generatedAt = new Date().toISOString()) {
  return {
    schema: PRESCREEN_SCHEMA,
    schema_version: PRESCREEN_SCHEMA_VERSION,
    rules_version: PRESCREEN_RULES_VERSION,
    input_hash: hashValue(input),
    generated_at: generatedAt,
  };
}

function reason(code, gate, message, evidence = null) {
  return { code, gate, message, evidence };
}

function gateState(input, name) {
  const value = input?.gates?.[name];
  return value && GATE_STATES.has(value.status) ? value : null;
}

/**
 * Evaluate already-extracted evidence. This deliberately does not infer facts
 * from prose: callers classify JD/profile evidence, then every path shares the
 * same terminal rules here.
 */
export function evaluatePrescreen(input, { generatedAt } = {}) {
  const metadata = createPrescreenMetadata(input, generatedAt);
  const failures = [];
  const uncertainties = [];
  const missing = [];

  if (!input || typeof input !== 'object') missing.push('input');
  if (input?.complete_jd !== true) missing.push('complete_jd');
  if (input?.assessment_complete !== true) missing.push('assessment_complete');

  for (const name of HARD_GATES) {
    const gate = gateState(input, name);
    if (!gate) {
      missing.push(`gates.${name}`);
    } else if (gate.status === 'fail') {
      failures.push(reason(`${name}_failed`, name, gate.reason || `${name} gate failed`, gate.evidence ?? null));
    } else if (gate.status === 'unknown') {
      uncertainties.push(reason(`${name}_unknown`, name, gate.reason || `${name} is unknown`, gate.evidence ?? null));
    }
  }

  const years = input?.years;
  if (!years || !Number.isFinite(years.required) || years.required < 0
      || (years.verified !== null && (!Number.isFinite(years.verified) || years.verified < 0))) {
    missing.push('years');
  } else if (years.verified === null) {
    uncertainties.push(reason('years_unverified', 'years', 'Relevant tenure requires confirmation', years.evidence ?? null));
  } else {
    const gap = years.required - years.verified;
    if (gap >= 3) failures.push(reason('years_gap_terminal', 'years', `Verified experience is ${gap} years below the stated minimum`, years.evidence ?? null));
    else if (gap > 0) uncertainties.push(reason('years_gap_borderline', 'years', `Verified experience is ${gap} year${gap === 1 ? '' : 's'} below the stated minimum`, years.evidence ?? null));
  }

  if (!Array.isArray(input?.core_capabilities)) {
    missing.push('core_capabilities');
  } else {
    if (input.core_capabilities.some((item) => !item?.name || typeof item.core !== 'boolean' || typeof item.mandatory !== 'boolean' || !['proven', 'adjacent', 'gap', 'unverified'].includes(item.match))) missing.push('core_capabilities.items');
    const gaps = input.core_capabilities.filter((item) => item?.core === true && item?.mandatory === true && item?.match === 'gap');
    if (gaps.length >= 2) failures.push(reason('multiple_core_capability_gaps', 'core_capabilities', `Missing ${gaps.length} core mandatory capabilities: ${gaps.map((item) => item.name).join(', ')}`, gaps.map((item) => item.evidence ?? null)));
    for (const item of input.core_capabilities.filter((entry) => entry?.core === true && entry?.mandatory === true && ['adjacent', 'unverified'].includes(entry?.match))) {
      const code = item.match === 'adjacent' ? 'core_capability_adjacent' : 'core_capability_unverified';
      uncertainties.push(reason(code, 'core_capabilities', `${item.name} is ${item.match}`, item.evidence ?? null));
    }
  }

  if (!Array.isArray(input?.credentials)) {
    missing.push('credentials');
  } else {
    for (const item of input.credentials.filter((entry) => entry?.mandatory === true)) {
      if (item.status === 'absent') failures.push(reason('mandatory_credential_absent', 'credentials', `Mandatory credential absent: ${item.name}`, item.evidence ?? null));
      else if (item.status !== 'present') uncertainties.push(reason('mandatory_credential_unverified', 'credentials', `Mandatory credential unverified: ${item.name}`, item.evidence ?? null));
    }
  }

  const status = failures.length ? 'fail' : missing.length ? 'incomplete' : uncertainties.length ? 'uncertain' : 'pass';
  return { ...metadata, status, discard_reasons: failures, uncertainties, missing };
}

export function validatePrescreenResult(result) {
  const errors = [];
  if (!result || typeof result !== 'object') return { valid: false, errors: ['result must be an object'] };
  if (result.schema !== PRESCREEN_SCHEMA) errors.push('schema mismatch');
  if (result.schema_version !== PRESCREEN_SCHEMA_VERSION) errors.push('schema_version mismatch');
  if (result.rules_version !== PRESCREEN_RULES_VERSION) errors.push('rules_version mismatch');
  if (!PRESCREEN_STATUSES.includes(result.status)) errors.push('invalid status');
  if (!/^[a-f0-9]{64}$/.test(result.input_hash || '')) errors.push('invalid input_hash');
  if (!Array.isArray(result.discard_reasons) || !Array.isArray(result.uncertainties) || !Array.isArray(result.missing)) errors.push('reason arrays are required');
  const malformedReason = [...(result.discard_reasons || []), ...(result.uncertainties || [])]
    .some((entry) => !entry?.code || !entry?.gate || !entry?.message);
  if (malformedReason) errors.push('reasons require code, gate, and message');
  if (result.status === 'fail' && result.discard_reasons?.length === 0) errors.push('fail requires discard_reasons');
  return { valid: errors.length === 0, errors };
}

export function isReusablePrescreen(result, input) {
  return validatePrescreenResult(result).valid
    && result.status !== 'incomplete'
    && result.input_hash === hashValue(input);
}

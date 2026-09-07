#!/usr/bin/env node
/** Build one source-grounded preparation plan for a single role. */

import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { extractJdSkills, classifySkillGaps, diagnoseExtraction } from './jd-skill-gap.mjs';
import { canonicalize, extractSkills } from './skill-extract.mjs';
import { hashValue } from './lib/prescreen-core.mjs';

export const PREPARATION_PLAN_SCHEMA = 'career-ops/preparation-plan';
export const PREPARATION_PLAN_VERSION = 1;
const CLASSIFICATIONS = new Set(['evidenced', 'evidence_gap', 'adjacent', 'actual_gap', 'unverified']);

export function parseReportClassifications(reportText = '') {
  const mappings = [];
  for (const line of reportText.split('\n')) {
    if (!/^\s*\|/.test(line)) continue;
    const cells = line.split('|').slice(1, -1).map((cell) => cell.trim());
    const index = cells.findIndex((cell) => /^(proven|adjacent|gap|unverified)$/i.test(cell));
    if (index === -1) continue;
    const requirement = cells.slice(0, index).reverse().find((cell) => cell && !/^#?\d+$/.test(cell));
    if (!requirement || /^[-: ]+$/.test(requirement)) continue;
    const classification = ({ proven: 'evidenced', adjacent: 'adjacent', gap: 'actual_gap', unverified: 'unverified' })[cells[index].toLowerCase()];
    mappings.push({ requirement, classification, evidence: cells[index + 1] || null, source: 'report' });
  }
  return mappings;
}

function item(requirement, classification, evidence, source) {
  if (!CLASSIFICATIONS.has(classification)) throw new Error(`invalid preparation classification: ${classification}`);
  return { requirement, classification, evidence: evidence || null, source };
}

export function buildPreparationPlan({ company, role, jdText, cvText, profileText = '', reportText = '', sources = {}, generatedAt = new Date().toISOString() }) {
  if (!company || !role || !jdText?.trim()) throw new Error('company, role, and non-empty jdText are required');
  const jdSkills = extractJdSkills(jdText);
  const diagnosis = diagnoseExtraction(jdText, jdSkills);
  const classified = classifySkillGaps(jdSkills, cvText || '');
  const profileSkills = extractSkills(profileText);
  const byKey = new Map();

  for (const skill of classified.existing) byKey.set(canonicalize(skill).toLowerCase(), item(skill, 'evidenced', 'Named in cv.md Skills', sources.cv || 'cv.md'));
  for (const skill of classified.supportedByResume) byKey.set(canonicalize(skill).toLowerCase(), item(skill, 'evidence_gap', 'Present in CV prose but not the Skills section', sources.cv || 'cv.md'));
  for (const skill of classified.gap) {
    const knownInProfile = profileSkills.has(canonicalize(skill));
    byKey.set(canonicalize(skill).toLowerCase(), item(
      skill,
      knownInProfile ? 'evidence_gap' : 'actual_gap',
      knownInProfile ? 'Named in profile but not evidenced in cv.md' : 'No evidence found in approved candidate sources',
      knownInProfile ? (sources.profile || 'config/profile.yml') : `${sources.cv || 'cv.md'}; ${sources.profile || 'config/profile.yml'}`,
    ));
  }

  for (const mapping of parseReportClassifications(reportText)) {
    byKey.set(canonicalize(mapping.requirement).toLowerCase(), mapping);
  }
  if (diagnosis) byKey.set('jd requirements', item('JD requirements', 'unverified', diagnosis.message, sources.jd || 'JD'));

  const requirements = [...byKey.values()].sort((a, b) => a.requirement.localeCompare(b.requirement));
  const actionsFor = (section) => requirements.filter((entry) => entry.classification !== 'evidenced').map((entry) => ({
    requirement: entry.requirement,
    classification: entry.classification,
    action: section === 'pre_application'
      ? ({
          evidence_gap: 'Verify the existing evidence; strengthen only from an approved source.',
          adjacent: 'State the adjacent evidence and the boundary; do not claim direct experience.',
          actual_gap: 'Do not claim this capability; decide whether focused learning is worth the application.',
          unverified: 'Resolve from the JD, an approved source, or a recruiter question before relying on it.',
        })[entry.classification]
      : ({
          evidence_gap: 'Prepare one source-backed example and its limits.',
          adjacent: 'Prepare a bridge answer from the adjacent experience to the requirement.',
          actual_gap: 'Prepare an honest gap-and-learning answer.',
          unverified: 'Prepare a clarifying question and avoid assumptions.',
        })[entry.classification],
  }));

  return {
    schema: PREPARATION_PLAN_SCHEMA,
    schema_version: PREPARATION_PLAN_VERSION,
    metadata: {
      generated_at: generatedAt,
      source_hash: hashValue({ jdText, cvText, profileText, reportText }),
      sources: { jd: sources.jd || null, cv: sources.cv || 'cv.md', profile: sources.profile || 'config/profile.yml', report: sources.report || null },
    },
    role: { company, title: role },
    requirements,
    pre_application: actionsFor('pre_application'),
    interview_preparation: actionsFor('interview_preparation'),
  };
}

export function validatePreparationPlan(plan) {
  const errors = [];
  if (plan?.schema !== PREPARATION_PLAN_SCHEMA || plan?.schema_version !== PREPARATION_PLAN_VERSION) errors.push('schema mismatch');
  if (!plan?.role?.company || !plan?.role?.title) errors.push('role is required');
  if (!/^[a-f0-9]{64}$/.test(plan?.metadata?.source_hash || '')) errors.push('metadata.source_hash is required');
  if (!Array.isArray(plan?.requirements) || plan.requirements.some((entry) => !CLASSIFICATIONS.has(entry.classification))) errors.push('invalid requirements');
  if (!Array.isArray(plan?.pre_application) || !Array.isArray(plan?.interview_preparation)) errors.push('preparation sections are required');
  return { valid: errors.length === 0, errors };
}

async function main() {
  const args = process.argv.slice(2);
  const value = (flag) => { const index = args.indexOf(flag); return index === -1 ? null : args[index + 1]; };
  const jd = value('--jd');
  const company = value('--company');
  const role = value('--role');
  if (!jd || !company || !role) throw new Error('Usage: node preparation-plan.mjs --jd FILE --company NAME --role TITLE [--report FILE] [--output FILE]');
  const read = (path, required = false) => {
    try { return readFileSync(path, 'utf8'); }
    catch (error) { if (required) throw error; return ''; }
  };
  const report = value('--report');
  const plan = buildPreparationPlan({
    company,
    role,
    jdText: read(jd, true),
    cvText: read('cv.md'),
    profileText: read('config/profile.yml'),
    reportText: report ? read(report, true) : '',
    sources: { jd, cv: 'cv.md', profile: 'config/profile.yml', report },
  });
  const output = value('--output');
  if (output) {
    mkdirSync(dirname(resolve(output)), { recursive: true });
    writeFileSync(output, `${JSON.stringify(plan, null, 2)}\n`);
  }
  console.log(JSON.stringify(plan, null, 2));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch((error) => {
    console.error(`preparation-plan: ${error.message}`);
    process.exitCode = 1;
  });
}

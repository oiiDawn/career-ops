/** Verify action boundaries, hard-gate precedence and deterministic action ordering. */
import assert from 'node:assert/strict';
import { classifyOpportunity, orderOpportunities } from '../scoring-decisions.mjs';
const gates = Object.fromEntries(['location', 'employment', 'size', 'compensation', 'eligibility', 'liveness'].map(k => [k, 'Pass']));
const score = (lower, upper, coverage = 1) => ({ lower, upper, coverage });
assert.equal(classifyOpportunity(score(3, 5, 0.5), gates, 4), 'apply');
assert.equal(classifyOpportunity(score(3, 4, 0.5), gates, 4), 'deprioritize');
assert.equal(classifyOpportunity(score(5, 5), { ...gates, employment: 'Fail' }, 4), 'discard');
assert.equal(classifyOpportunity(score(4.5, 5), { ...gates, size: 'Unknown' }, 4), 'apply');
assert.throws(() => classifyOpportunity(score(4, 4), gates, undefined));
assert.throws(() => classifyOpportunity(score(4, 4), {}, 4));
assert.throws(() => classifyOpportunity(score(4, 3), gates, 4));
const item = (id, lower, effort_days, deadline = null) => ({ id, score: score(lower, 5, 0.35), gates, ready: false, deadline, effort_days });
const inputs = [item('hard', 2.5, 5), item('easy', 1.5, 1), item('urgent', 1, null, '2026-09-12')];
assert.deepEqual(orderOpportunities(inputs, 4).map(x => x.id), ['urgent', 'easy', 'hard']);
assert.deepEqual(orderOpportunities([...inputs].reverse(), 4), orderOpportunities(inputs, 4));
assert.throws(() => orderOpportunities([inputs[0], inputs[0]], 4));
assert.throws(() => orderOpportunities([{ ...inputs[0], deadline: '2026-02-30' }], 4));
console.log('scoring-decisions: thresholds, gates, effort and stable ordering passed');

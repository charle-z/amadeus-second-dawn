'use strict';

// Result views are pure: no DOM, network or model calls.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load() {
  const context = { window: {} };
  const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'results.js'), 'utf8');
  vm.runInNewContext(source, context, { filename: 'results.js' });
  return context.window.AmadeusResults;
}
function evidence(name) {
  return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'evidence', name), 'utf8'));
}
const trial = (overrides = {}) => ({ strategy: 'NAIVE_MEMORY', scenario: 'stable', world_version: 'v1', seed: 7,
  action: 'left', outcome: 'dead', inspection: null, assessment: null, model_calls: [], ...overrides });

test('hint correctness is read back from action and recorded outcome only', () => {
  const R = load();
  const cases = [
    ['left', 'left', 'won', true, true], ['left', 'left', 'dead', true, false],
    ['left', 'right', 'won', false, false], ['left', 'right', 'dead', false, true],
  ];
  for (const [hint, action, outcome, followed, correct] of cases) {
    const info = R.hintInfo(trial({ inspection: { hint }, action, outcome }));
    assert.deepEqual({ ...info }, { hint, followed, correct });
  }
  assert.deepEqual({ ...R.hintInfo(trial()) }, { hint: null, followed: null, correct: null });
  assert.equal(R.hintInfo(trial({ inspection: { hint: 'left' }, outcome: 'killed' })).correct, null);
});

test('the matrix keeps strategy and scenario positions and marks gaps', () => {
  const R = load();
  const run = { trials: [trial({ strategy: 'VERIFIED_MEMORY', scenario: 'shifted' }), trial({ strategy: 'NO_MEMORY' })] };
  const model = R.matrixModel(run);
  assert.deepEqual([...model.columns], ['stable', 'shifted']);
  // Arrays built inside the vm realm are copied before comparing.
  assert.deepEqual([...model.rows.map(r => r.strategy)], ['NO_MEMORY', 'VERIFIED_MEMORY']);
  assert.equal(model.rows[0].cells[1], null);
  assert.equal(model.rows[1].cells[1].scenario, 'shifted');
  assert.equal(model.preFix, false);
  assert.equal(R.matrixModel({ trials: [trial({ world_version: 'v2' })] }).preFix, true);
  const cells = { cells: [{ strategy: 'NAIVE_MEMORY', trials: [trial()] }, { strategy: 'VERIFIED_MEMORY', trials: [] }] };
  assert.deepEqual([...R.matrixModel(cells, ['NAIVE_MEMORY', 'VERIFIED_MEMORY']).rows.map(r => r.cells[0] && r.cells[0].strategy)],
    ['NAIVE_MEMORY', null]);
});

test('the last action rationale is quoted, not the assessment', () => {
  const R = load();
  const t = trial({ model_calls: [
    { stage: 'assess', response: { verdict: 'uncertain', rationale: 'assessment text' } },
    { stage: 'act', response: { action: 'left', rationale: 'action text' } }] });
  assert.equal(R.lastRationale(t), 'action text');
});

test('the headline tally reproduces the published evidence', () => {
  const R = load();
  const runs = [evidence('comparison-seed-7.json').comparison, evidence('ui-comparison-seed-7.json').comparison,
    evidence('ui-post-fix-seed-7.json').comparison, evidence('cells-seed-7.json').cell_run,
    { trials: [evidence('matched-single-trial.json').trial] }];
  const t = R.tally(runs);
  assert.equal(t.trials, 23);
  assert.equal(t.survived, 3);
  assert.equal(t.inspected, 19);
  assert.equal(t.followed, 18);
  assert.equal(t.hintWrong, 19);
  assert.deepEqual({ ...t.verdicts }, { uncertain: 9 });
});

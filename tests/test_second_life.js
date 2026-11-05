'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
const first = source.indexOf('function secondLifeState(');
const last = source.indexOf('\nfunction renderSecondLife()', first);
assert.ok(first >= 0 && last > first, 'Second Life state selector exists');
const select = vm.runInNewContext(source.slice(first, last) + '\nsecondLifeState');

const memory = {id: 11, generation_id: 1, world_version: 'v1', seed: 7, action: 'left', outcome: 'dead'};
const parent = {id: 1, world_version: 'v1', seed: 7, status: 'dead', parent_id: null, events: []};
const child = {id: 2, world_version: 'v2', seed: 7, status: 'alive', parent_id: 1, events: []};
const state = {generations: [child, parent], memories: [memory]};

test('the chain requires an actual v1 memory and finished life', () => {
  assert.equal(select(state, 1).stage, 'ready');
  assert.equal(select({...state, memories: []}, 1).stage, 'need-memory');
  assert.equal(select({...state, generations: [{...parent, status: 'alive'}]}, 1).stage, 'need-memory');
  assert.equal(select(state, 99).stage, 'select');
});

test('a linked v2 life waits for verification; no outcome is invented', () => {
  const result = select(state, 2);
  assert.equal(result.stage, 'verify');
  assert.equal(result.memory.id, 11);
  assert.equal(result.trial, undefined);
  assert.equal(select({...state, generations: [{...child, seed: 8}, parent]}, 2).stage, 'unrelated');
  assert.equal(select({...state, generations: [{...child, status: 'killed'}, parent]}, 2).stage, 'ended');
});

test('a persisted verified event is recovered on a fresh state read', () => {
  const trial = {assessment: {verdict: 'uncertain'}, action: 'right', outcome: 'dead'};
  const loaded = JSON.parse(JSON.stringify({...state, generations: [{...child, status: 'dead', events: [{kind: 'verified_trial', data: trial}]}, parent]}));
  const result = select(loaded, 2);
  assert.equal(result.stage, 'completed');
  assert.equal(result.trial.assessment.verdict, 'uncertain');
  assert.equal(result.trial.outcome, 'dead');
});


test('an interrupted attempt stays incomplete and can be retried', () => {
  const interrupted = {stage: 'act', model_calls: [{stage: 'assess'}], usage: null, error_type: 'RuntimeError'};
  const loaded = JSON.parse(JSON.stringify({...state, generations: [{...child, events: [{kind: 'verified_interrupted', data: interrupted}]}, parent]}));
  const result = select(loaded, 2);
  assert.equal(result.stage, 'verify');
  assert.equal(result.interrupted.stage, 'act');
  assert.equal(result.interrupted.model_calls.length, 1);
  assert.equal(result.trial, undefined);
});

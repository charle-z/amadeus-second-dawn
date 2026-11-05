'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
const start = source.indexOf('function workPaths(');
const end = source.indexOf('\nfunction renderWork(', start);
assert.ok(start >= 0 && end > start, 'work state helpers exist');
const helpers = vm.runInNewContext(source.slice(start, end) + '\n({workPaths, workState, workDiagnosticText})');

test('paths are explicit, one per line, and blank lines are ignored', () => {
  assert.deepEqual(Array.from(helpers.workPaths(' README.md\n\ndocs/plan.md \n')), ['README.md', 'docs/plan.md']);
});
test('task selection survives reload and never invents an analysis', () => {
  const state = {work_available: true, work_tasks: [{id: 2, goal: 'Track changes', paths: ['a.md'], last_result: null}]};
  const loaded = JSON.parse(JSON.stringify(state));
  assert.equal(helpers.workState(loaded, 2).task.goal, 'Track changes');
  assert.equal(helpers.workState(loaded, 2).task.last_result, null);
  assert.equal(helpers.workState(loaded, 9).task.id, 2);
  assert.equal(helpers.workState({work_available: false, work_tasks: []}, null).available, false);
});


test('syntax diagnostics show the actual check, status and position without claiming correctness', () => {
  assert.equal(helpers.workDiagnosticText({path: 'app.py', check: 'python_syntax', status: 'error', line: 7, column: 2}), 'app.py · python_syntax · error · line 7, column 2');
  assert.equal(helpers.workDiagnosticText({path: 'data.json', check: 'json_syntax', status: 'ok'}), 'data.json · json_syntax · ok');
});

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
const start = source.indexOf('function workPaths(');
const end = source.indexOf('\nfunction renderWork(', start);
assert.ok(start >= 0 && end > start, 'work state helpers exist');
const helpers = vm.runInNewContext(source.slice(start, end) + '\n({workPaths, workState, workDiagnosticText, confirmWorkDelete, workHistory})');

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


test('deleting a task requires explicit confirmation and explains limits', () => {
  let prompt = '';
  assert.equal(helpers.confirmWorkDelete(message => { prompt = message; return false; }), false);
  assert.match(prompt, /snapshot/i);
  assert.match(prompt, /backup/i);
  assert.match(prompt, /Meta/i);
  assert.equal(helpers.confirmWorkDelete(() => true), true);
});


test('review history keeps recorded timestamps and marks legacy unknown without fabricating one', () => {
  const task = {review_history: [{recorded_at: '2026-11-05T01:03:13Z', result: {analysis: {summary: 'recent'}}}, {recorded_at: null, result: {analysis: {summary: 'legacy'}}}]};
  const entries = helpers.workHistory(task);
  assert.equal(entries.length, 2);
  assert.equal(entries[0].label, '2026-11-05T01:03:13Z');
  assert.equal(entries[0].result.analysis.summary, 'recent');
  assert.equal(entries[1].label, 'legacy date unknown');
  assert.equal(entries[1].result.analysis.summary, 'legacy');
  assert.equal(helpers.workHistory({}).length, 0);
});


test('rendered history keeps the latest visible and folds real earlier evidence as text', () => {
  class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; this.textContent = ''; }
  }
  const ids = {};
  const get = id => ids[id] || (ids[id] = new Node('div'));
  const make = (tag, text, className) => { const n = new Node(tag); n.textContent = text == null ? '' : String(text); n.className = className; return n; };
  const details = (title, value) => { const n = make('details'); n.append(make('summary', title), make('pre', JSON.stringify(value))); return n; };
  const newest = {analysis: {summary: 'latest finding', findings: [], next_step: 'inspect'}};
  const old = {changes: [{path: 'a.py', status: 'changed', diff: '<img src=x>'}], diagnostics: [{path: 'a.py', check: 'python-syntax', status: 'pass'}], analysis: {summary: 'old finding', findings: [{path: 'a.py', quote: '<script>literal</script>', assessment: 'historical'}], next_step: 'review'}};
  const state = {work_available: true, work_tasks: [{id: 2, goal: 'goal', paths: ['a.py'], last_result: newest, review_history: [{recorded_at: '2026-11-05T01:03:13Z', result: newest}, {recorded_at: null, result: old}]}]};
  const section = source.slice(start, source.indexOf('\nasync function workAction(', end));
  const context = {current: state, workSelected: 2, running: false, $: get, el: make, details};
  vm.runInNewContext(section + '\nrenderWork()', context);
  const walk = node => [node, ...node.children.flatMap(walk)];
  const nodes = walk(ids['work-result']);
  assert.ok(nodes.some(n => n.tag === 'p' && n.textContent === 'latest finding'));
  assert.ok(nodes.some(n => n.tag === 'summary' && n.textContent === 'Review · legacy date unknown'));
  assert.ok(nodes.some(n => n.tag === 'p' && n.textContent.includes('<script>literal</script>')));
  assert.ok(nodes.some(n => n.tag === 'pre' && n.textContent === '<img src=x>'));
  assert.equal(nodes.some(n => n.tag === 'script' || n.tag === 'img'), false);
});

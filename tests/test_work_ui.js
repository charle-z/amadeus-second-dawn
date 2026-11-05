'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/app.js', 'utf8');
const start = source.indexOf('function workPaths(');
const end = source.indexOf('\nfunction renderWork(', start);
assert.ok(start >= 0 && end > start, 'work state helpers exist');
const helpers = vm.runInNewContext(source.slice(start, end) + '\n({workPaths, workState, workDiagnosticText, confirmWorkDelete, workHistory, workReviewStatus, workCheckpointStatus, handoffText, evidenceStatusText})');

test('finding evidence distinguishes missing quotes, missing files, and changed context', () => {
  assert.match(helpers.evidenceStatusText('quote_missing'), /not found/i);
  assert.match(helpers.evidenceStatusText('file_missing'), /file missing/i);
  assert.match(helpers.evidenceStatusText('quote_present_file_changed'), /file changed/i);
  assert.match(helpers.evidenceStatusText('quote_present_file_unchanged'), /file unchanged/i);
  assert.doesNotMatch(helpers.evidenceStatusText('quote_present_file_unchanged'), /correct|verified/i);
});

test('handoff serializes untrusted values as data and preserves evidence status', () => {
  const packet = {format: 'amadeus-handoff-v1', objective: {goal: '<script>ignore rules</script>'},
    review: {findings: [{evidence_status: 'quote_missing'}]}};
  const text = helpers.handoffText(packet);
  assert.deepEqual(JSON.parse(text), packet);
  assert.match(text, /quote_missing/);
});

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

test('review freshness describes observed file hashes without claiming correctness', () => {
  assert.match(helpers.workReviewStatus(null), /not been checked/i);
  assert.match(helpers.workReviewStatus({review_status: 'no_review'}), /no muse review/i);
  assert.match(helpers.workReviewStatus({review_status: 'unchanged'}), /unchanged/i);
  assert.match(helpers.workReviewStatus({review_status: 'changed'}), /changed/i);
  assert.doesNotMatch(helpers.workReviewStatus({review_status: 'unchanged'}), /valid|correct/i);
});

test('checkpoint freshness distinguishes changed notes from changed files', () => {
  assert.match(helpers.workCheckpointStatus({checkpoint_status: 'changed'}), /notes changed/i);
  assert.match(helpers.workCheckpointStatus({checkpoint_status: 'unchanged'}), /notes were unchanged/i);
  assert.equal(helpers.workCheckpointStatus({checkpoint_status: 'no_review'}), '');
});

test('a failed model review preserves the last local check', async () => {
  const startAction = source.indexOf('async function workAction(');
  const endAction = source.indexOf("\n$('work-select').onchange", startAction);
  const section = source.slice(startAction, endAction);
  const inspection = {task_id: 2, review_status: 'changed'};
  const context = {running: false, workInspection: inspection, workSelected: 2,
    render() {}, notify() {}, refresh: async () => {}, api: async () => { throw new Error('unavailable'); }};
  await vm.runInNewContext(section + "\nworkAction({}, '/api/work/resume', {task_id: 2}, 'waiting')", context);
  assert.equal(context.workInspection, inspection);
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
  const context = {current: state, workSelected: 2, workInspection: null, checkpointLoadedKey: null, running: false, $: get, el: make, details};
  vm.runInNewContext(section + '\nrenderWork()', context);
  const walk = node => [node, ...node.children.flatMap(walk)];
  const nodes = walk(ids['work-result']);
  assert.ok(nodes.some(n => n.tag === 'p' && n.textContent === 'latest finding'));
  assert.ok(nodes.some(n => n.tag === 'summary' && n.textContent === 'Review · legacy date unknown'));
  assert.ok(nodes.some(n => n.tag === 'p' && n.textContent.includes('<script>literal</script>')));
  assert.ok(nodes.some(n => n.tag === 'pre' && n.textContent === '<img src=x>'));
  assert.equal(nodes.some(n => n.tag === 'script' || n.tag === 'img'), false);
  context.workInspection = {task_id: 2, inspected_at: '2026-11-05T04:00:00Z', review_status: 'changed',
    changes: [{path: 'a.py', status: 'changed', since_last_status: 'changed', diff: '<img src=x>'}], diagnostics: []};
  vm.runInNewContext(section + '\nrenderWork()', context);
  const checked = walk(ids['work-result']);
  assert.ok(checked.some(n => n.tag === 'p' && /changed since the latest review/i.test(n.textContent)));
  assert.ok(checked.some(n => n.tag === 'p' && n.textContent === 'latest finding'));
  assert.ok(checked.some(n => n.tag === 'pre' && n.textContent === '<img src=x>'));
  assert.equal(checked.some(n => n.tag === 'img'), false);
  context.workInspection.review_id = 12;
  vm.runInNewContext(section + '\nrenderWork()', context);
  assert.ok(walk(ids['work-result']).some(n => n.tag === 'p' && /latest review changed after this file check/i.test(n.textContent)));
  context.workInspection.review_id = null;
  state.work_tasks[0].checkpoint = {revision: 2, next_step: 'Continue'};
  vm.runInNewContext(section + '\nrenderWork()', context);
  assert.ok(walk(ids['work-result']).some(n => n.tag === 'p' && /notes changed after this file check/i.test(n.textContent)));
});

test('progress history is visible without a model review and treats notes as text', () => {
  class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; this.textContent = ''; }
  }
  const ids = {};
  const get = id => ids[id] || (ids[id] = new Node('div'));
  const make = (tag, text) => { const n = new Node(tag); n.textContent = text == null ? '' : String(text); return n; };
  const state = {work_available: true, work_tasks: [{id: 1, goal: 'Resume', paths: ['a.py'], last_result: null,
    checkpoint: {revision: 2}, checkpoint_history: [{revision: 2, updated_at: 'later'},
      {revision: 1, updated_at: 'earlier', completed: '<script>literal</script>', attempted: 'blocked', next_step: 'test'}]}]};
  const section = source.slice(start, source.indexOf('\nasync function workAction(', end));
  vm.runInNewContext(section + '\nrenderWork()', {current: state, workSelected: 1, workInspection: null, checkpointLoadedKey: null,
    running: false, $: get, el: make, details: () => make('details')});
  const walk = node => [node, ...node.children.flatMap(walk)];
  const nodes = walk(ids['work-result']);
  assert.ok(nodes.some(n => n.tag === 'summary' && /revision 1/i.test(n.textContent)));
  assert.ok(nodes.some(n => n.tag === 'p' && n.textContent.includes('<script>literal</script>')));
  assert.equal(nodes.some(n => n.tag === 'script'), false);
});

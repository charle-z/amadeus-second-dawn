'use strict';
const $ = id => document.getElementById(id);
const R = window.AmadeusResults;
let selected = null;
let workSelected = null;
let workInspection = null;
let checkpointLoadedKey = null;
let current = {generations: [], memories: [], comparisons: [], cell_runs: []};
let running = false;

const OUTCOME_WORD = {won: 'Survived', dead: 'Died', killed: 'Killed', alive: 'Alive'};
const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function el(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = String(text);
  if (className) n.className = className;
  return n;
}
function clear(node) { node.replaceChildren(); node.classList.remove('empty'); }
function empty(node, text) { node.replaceChildren(); node.textContent = text; node.classList.add('empty'); }
function notify(text, error = false) {
  $('notice').hidden = !text;
  $('notice').textContent = text;
  $('notice').classList.toggle('error', error);
}
function details(title, value) {
  const node = el('details', null, 'raw');
  node.append(el('summary', title), el('pre', JSON.stringify(value, null, 2)));
  return node;
}
function clip(text, max) {
  const value = String(text || '').trim();
  return value.length > max ? value.slice(0, max - 1).trimEnd() + '…' : value;
}
async function api(path, body) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
async function refresh() {
  current = await api('/api/state');
  if (!current.generations.some(g => g.id === selected)) selected = current.generations[0]?.id ?? null;
  render();
}

function render() {
  const gen = current.generations.find(g => g.id === selected);
  window.renderWorld(gen);
  $('selected-title').textContent = gen ? `Generation ${gen.id} · ${gen.world_version} · seed ${gen.seed}` : 'No generation selected';
  $('selected-status').textContent = gen ? (OUTCOME_WORD[gen.status] || gen.status) : '—';
  $('selected-status').className = `badge outcome-${gen?.status || 'none'}`;
  $('observation').textContent = gen ? `“${gen.observation.scene} ${gen.observation.goal}”` : 'Start a generation to see what Muse observes.';
  $('start').disabled = running;
  $('step').disabled = !gen || gen.status !== 'alive' || running;
  $('restart').disabled = !gen || running;
  $('generation-count').textContent = String(current.generations.length);
  $('memory-count').textContent = String(current.memories.length);
  renderFinding(); renderGenerations(); renderMemories(); renderComparisons(); renderCells(); renderSecondLife(); renderWork();
}

// Derive the story exclusively from persisted generations, memories and events.
function secondLifeState(state, selectedId) {
  const generations = state.generations || [];
  const memories = state.memories || [];
  const gen = generations.find(g => g.id === selectedId);
  if (!gen) return {stage: 'select'};
  if (gen.world_version === 'v1') {
    const memory = memories.find(m => m.generation_id === gen.id && m.world_version === 'v1');
    return {stage: memory && ['won', 'dead'].includes(gen.status) ? 'ready' : 'need-memory', gen, memory};
  }
  const parent = generations.find(g => g.id === gen.parent_id && g.world_version === 'v1');
  const memory = parent && memories.find(m => m.generation_id === parent.id && m.world_version === 'v1');
  if (!parent || !memory || gen.world_version !== 'v2' || gen.seed !== parent.seed) return {stage: 'unrelated'};
  const events = [...(gen.events || [])].reverse();
  const record = events.find(e => e.kind === 'verified_trial');
  const interrupted = events.find(e => e.kind === 'verified_interrupted');
  return {stage: record ? 'completed' : gen.status === 'alive' ? 'verify' : 'ended', gen, parent, memory,
    trial: record && record.data, interrupted: interrupted && interrupted.data};
}

function renderSecondLife() {
  const story = $('second-life-story'); story.replaceChildren();
  const state = secondLifeState(current, selected);
  $('continue-changed').disabled = running || state.stage !== 'ready';
  $('verified-step').disabled = running || state.stage !== 'verify';
  const fact = (label, value) => { const item = el('div', null, 'second-life-item'); item.append(el('strong', label), el('span', value)); story.append(item); };
  if (state.stage === 'select' || state.stage === 'unrelated') {
    fact('1 · Previous life', 'Select a v1 generation in the timeline and make a real Muse decision.'); return;
  }
  if (state.stage === 'need-memory') {
    fact('1 · Previous life', `Generation ${state.gen.id} · v1 · ${OUTCOME_WORD[state.gen.status] || state.gen.status}. A finished v1 decision is needed to create its memory.`); return;
  }
  const parent = state.parent || state.gen;
  fact('1 · Previous life', `Generation ${parent.id} · v1 · seed ${parent.seed}. Muse chose ${state.memory.action}; the backend recorded ${OUTCOME_WORD[state.memory.outcome] || state.memory.outcome}.`);
  fact('2 · Carried evidence', `Memory #${state.memory.id} belongs to generation ${parent.id}; its original version and outcome remain unchanged.`);
  if (state.stage === 'ready') {
    fact('3 · Changed world', 'Continue to create a linked v2 life with the same seed. This makes no model call.'); return;
  }
  fact('3 · Changed world', `Generation ${state.gen.id} · v2 · seed ${state.gen.seed} · child of generation ${parent.id}. The gate rule is reversed.`);
  if (state.stage === 'verify') {
    if (state.interrupted) {
      fact('4 · Interrupted attempt', 'The last attempt did not complete. No outcome was recorded; you can retry.');
      story.append(details('Incomplete attempt evidence', state.interrupted));
    } else {
      fact('4 · Verification and decision', 'Not run yet. Ask Muse to assess the old memory and choose using the current, fallible inspection.');
    }
    return;
  }
  if (state.stage === 'ended') {
    fact('4 · Verification and decision', `This life ended as ${OUTCOME_WORD[state.gen.status] || state.gen.status} without a recorded verified trial.`); return;
  }
  const trial = state.trial;
  if (trial.inspection) fact('4 · Current inspection', `Hint: ${trial.inspection.hint}. This signal can be wrong.`);
  if (trial.assessment) fact('5 · Muse assesses the memory', `${trial.assessment.verdict} — ${trial.assessment.rationale}`);
  if (trial.action && trial.outcome) fact('6 · Recorded outcome', `Muse chose ${trial.action}; the backend recorded ${OUTCOME_WORD[trial.outcome] || trial.outcome}.`);
  story.append(details('Full recorded evidence', trial));
  if (state.interrupted) story.append(details('Earlier incomplete attempt', state.interrupted));
}

function workPaths(text) {
  return String(text || '').split(/\r?\n/).map(path => path.trim()).filter(Boolean);
}
function workState(state, selectedId) {
  const tasks = Array.isArray(state.work_tasks) ? state.work_tasks : [];
  return {available: state.work_available === true, tasks,
    task: tasks.find(item => item.id === selectedId) || tasks[0] || null};
}
function workDiagnosticText(item) {
  let text = `${item.path} · ${item.check} · ${item.status}`;
  if (Number.isInteger(item.line) && item.line > 0) {
    text += ` · line ${item.line}`;
    if (Number.isInteger(item.column) && item.column > 0) text += `, column ${item.column}`;
  }
  return text;
}
function confirmWorkDelete(confirmDialog) {
  return confirmDialog('Delete this saved objective, its snapshots, progress notes and its local analysis? This cannot erase backups, filesystem copies, public evidence, or data already sent to Meta.');
}
function workHistory(task) {
  const history = Array.isArray(task.review_history) ? task.review_history : [];
  return history.filter(item => item && item.result).map(item => ({
    label: typeof item.recorded_at === 'string' && item.recorded_at ? item.recorded_at : 'legacy date unknown',
    result: item.result,
  }));
}
function workReviewStatus(inspection) {
  if (!inspection) return 'The latest review has not been checked against current files.';
  if (inspection.review_status === 'no_review') return 'No Muse review exists for this objective.';
  if (inspection.review_status === 'unchanged') return 'Files were unchanged since the latest review.';
  return 'Files changed since the latest review; reconsider its recommendations.';
}
function workCheckpointStatus(inspection) {
  if (inspection?.checkpoint_status === 'changed') return 'Progress notes changed since the latest review; reconsider its recommendations.';
  if (inspection?.checkpoint_status === 'unchanged') return 'Progress notes were unchanged since the latest review.';
  return '';
}
function renderWork() {
  const view = workState(current, workSelected);
  const task = view.task;
  workSelected = task ? task.id : null;
  $('work-availability').textContent = view.available
    ? 'Workspace enabled. Only explicitly listed files are inspected.'
    : 'Workspace unavailable. Set AMADEUS_WORKSPACE on the server and restart it to use this feature.';
  $('work-start').disabled = running || !view.available;
  $('work-inspect').disabled = running || !view.available || !task;
  $('checkpoint-save').disabled = running || !view.available || !task;
  for (const id of ['checkpoint-completed', 'checkpoint-attempted', 'checkpoint-next']) $(id).disabled = running || !view.available || !task;
  $('work-resume').disabled = running || !view.available || !task;
  $('work-delete').disabled = running || !view.available || !task;
  $('work-select').disabled = running || !view.tasks.length;
  const selector = $('work-select'); selector.replaceChildren();
  if (!view.tasks.length) selector.append(el('option', 'No saved objectives'));
  for (const item of view.tasks) {
    const option = el('option', `#${item.id} · ${item.goal}`);
    option.value = String(item.id); option.selected = item.id === workSelected; selector.append(option);
  }
  const box = $('work-result'); box.replaceChildren();
  const checkpointKey = `${task?.id ?? ''}:${task?.checkpoint?.revision ?? 0}`;
  if (checkpointLoadedKey !== checkpointKey) {
    $('checkpoint-completed').value = task?.checkpoint?.completed || '';
    $('checkpoint-attempted').value = task?.checkpoint?.attempted || '';
    $('checkpoint-next').value = task?.checkpoint?.next_step || '';
    checkpointLoadedKey = checkpointKey;
  }
  if (!task) { box.textContent = 'No saved objectives yet.'; return; }
  box.append(el('strong', `Objective #${task.id}`), el('p', task.goal));
  box.append(el('div', `Monitoring: ${(task.paths || []).join(', ')}`, 'gen-meta'));
  const inspection = workInspection && workInspection.task_id === task.id ? workInspection : null;
  const reviewId = task.review_history?.[0]?.id ?? null;
  const reviewChanged = inspection && (inspection.review_id ?? null) !== reviewId;
  const statusText = reviewChanged ? 'The latest review changed after this file check; check again.'
    : !inspection && !task.last_result ? 'No Muse review exists for this objective.' : workReviewStatus(inspection);
  box.append(el('p', statusText, 'hint'));
  const notesChangedAfterCheck = inspection && (inspection.checkpoint_revision ?? 0) !== (task.checkpoint?.revision ?? 0);
  const noteStatus = notesChangedAfterCheck ? 'Progress notes changed after this file check; check again.'
    : !reviewChanged && inspection ? workCheckpointStatus(inspection) : '';
  if (noteStatus) box.append(el('p', noteStatus, 'hint'));
  if (inspection) {
    box.append(el('h3', 'Local file check'), el('p', `Checked at ${inspection.inspected_at}. Files can change afterwards.`, 'gen-meta'));
    appendWorkFiles(box, inspection);
  }
  const result = task.last_result;
  if (!result) { box.append(el('p', 'Snapshot saved. No Muse analysis has been run yet.', 'hint')); return; }
  const history = workHistory(task);
  if (history.length) box.append(el('p', `Latest review: ${history[0].label}`, 'gen-meta'));
  appendWorkReview(box, result);
  const older = history.slice(1);
  if (older.length) {
    box.append(el('h3', 'Earlier reviews'));
    for (const entry of older) {
      const panel = el('details', null, 'raw');
      panel.append(el('summary', `Review · ${entry.label}`));
      appendWorkReview(panel, entry.result);
      box.append(panel);
    }
    box.append(el('p', 'Up to five recent reviews are shown.', 'hint'));
  }
}
function appendWorkReview(box, result) {
  if (result.previous_analysis) {
    box.append(el('h3', 'Earlier analysis, reconsidered'),
      el('p', result.previous_analysis.summary),
      el('p', `Earlier proposed step: ${result.previous_analysis.next_step || '—'}`, 'gen-meta'));
    box.append(details('Earlier analysis and its citations', result.previous_analysis));
  }
  appendWorkFiles(box, result);
  const analysis = result.analysis;
  if (analysis) {
    box.append(el('h3', 'Muse analysis'), el('p', analysis.summary));
    for (const finding of analysis.findings || []) {
      const entry = el('div', null, 'work-finding');
      entry.append(el('strong', finding.path), el('p', `“${finding.quote}”`), el('p', finding.assessment));
      box.append(entry);
    }
    box.append(el('h3', 'Proposed next step'), el('p', analysis.next_step));
    box.append(el('p', 'This is a proposal, not an executed action. Check the evidence before acting.', 'hint'));
  }
  box.append(details('Recorded result and evidence', result));
}
function appendWorkFiles(box, result) {
  if (Array.isArray(result.changes)) {
    const heading = el('h3', 'File changes since the saved snapshot'); box.append(heading);
    for (const change of result.changes) {
      const recent = change.since_last_status && change.since_last_status !== 'not_compared'
        ? ` · since last review: ${change.since_last_status}` : '';
      box.append(el('p', `${change.path}: ${change.status}${recent}`));
      if (change.diff) {
        const panel = el('details', null, 'raw');
        panel.append(el('summary', `Difference for ${change.path}`), el('pre', change.diff));
        box.append(panel);
      }
    }
  }
  if (Array.isArray(result.diagnostics) && result.diagnostics.length) {
    box.append(el('h3', 'Deterministic syntax checks'));
    for (const diagnostic of result.diagnostics) box.append(el('p', workDiagnosticText(diagnostic)));
    box.append(el('p', 'Syntax checks do not establish functional correctness.', 'hint'));
  }
}
async function workAction(button, path, payload, waiting) {
  if (path !== '/api/work/resume') workInspection = null;
  running = true; render(); button.disabled = true; notify(waiting);
  try {
    const result = await api(path, payload);
    if (result.task) workSelected = result.task.id;
    if (path === '/api/work/delete') workSelected = null;
    if (path === '/api/work/resume') workInspection = null;
    if (path === '/api/work/inspect') workInspection = result;
    notify(path === '/api/work/start' ? 'Objective and file snapshot saved. No model call was made.' : path === '/api/work/delete' ? 'Local objective and snapshots deleted.' : path === '/api/work/checkpoint' ? 'Progress notes saved locally. No model call was made.' : path === '/api/work/inspect' ? 'Local check completed. No model call was made.' : 'Muse analysis saved. Check the evidence before acting.');
  } catch (error) { notify(error.message, true); }
  finally { running = false; await refresh().catch(error => notify(error.message, true)); }
}
$('work-select').onchange = event => { workInspection = null; workSelected = Number(event.target.value); renderWork(); };
$('work-start').onclick = () => {
  const goal = $('work-goal').value.trim();
  const paths = workPaths($('work-paths').value);
  if (!goal || !paths.length) return notify('Enter an objective and at least one relative file path.', true);
  workAction($('work-start'), '/api/work/start', {goal, paths}, 'Saving the objective and selected file snapshots…');
};
$('work-resume').onclick = () => workAction($('work-resume'), '/api/work/resume', {task_id: workSelected}, 'Comparing files and waiting for a real Muse analysis…');
$('work-inspect').onclick = () => workAction($('work-inspect'), '/api/work/inspect', {task_id: workSelected}, 'Checking selected files locally…');
$('checkpoint-save').onclick = () => workAction($('checkpoint-save'), '/api/work/checkpoint', {task_id: workSelected,
  completed: $('checkpoint-completed').value, attempted: $('checkpoint-attempted').value, next_step: $('checkpoint-next').value}, 'Saving progress notes locally…');
$('work-delete').onclick = () => {
  if (running || !workSelected || !confirmWorkDelete(message => window.confirm(message))) return;
  workAction($('work-delete'), '/api/work/delete', {task_id: workSelected}, 'Deleting the selected local objective…');
};

function renderFinding() {
  const box = $('finding');
  const runs = [...(current.comparisons || []), ...(current.cell_runs || [])];
  const t = R.tally(runs);
  box.replaceChildren();
  if (!t.trials) {
    box.append(el('p', 'No strategy comparison recorded yet. Give Muse one v1 decision, then run a comparison below.'));
    return;
  }
  const num = value => el('strong', value);
  const line = (...parts) => { const p = el('p'); parts.forEach(x => p.append(typeof x === 'string' ? document.createTextNode(x) : x)); return p; };
  box.append(el('span', 'So far, from the recorded runs below', 'finding-label'));
  box.append(line(num(`${t.survived} of ${t.trials}`), ' recorded decisions survived.'));
  if (t.inspected) {
    box.append(line('When Muse had an inspection hint, it followed it ', num(`${t.followed} of ${t.inspected}`),
      ' times. The hint was wrong in ', num(String(t.hintWrong)), ' of those trials.'));
  }
  const verdicts = Object.entries(t.verdicts);
  if (verdicts.length) {
    const total = verdicts.reduce((sum, [, n]) => sum + n, 0);
    box.append(line('Verified judged its memory ', ...verdicts.flatMap(([v, n], i) =>
      [i ? ', ' : '', num(`“${v}” ${n}`)]), ` of ${total} times.`));
  }
}

function renderGenerations() {
  const container = $('generations');
  if (!current.generations.length) return empty(container, 'No generations yet.');
  clear(container);
  for (const gen of current.generations) {
    const card = el('article', null, `gen${gen.id === selected ? ' selected' : ''}`);
    const head = el('div', null, 'gen-head');
    const btn = el('button', `Generation ${gen.id} · ${gen.world_version} · seed ${gen.seed}`, 'link');
    btn.onclick = () => { selected = gen.id; render(); };
    head.append(btn, el('span', OUTCOME_WORD[gen.status] || gen.status, `badge outcome-${gen.status}`));
    card.append(head, el('div', gen.parent_id ? `restarted from generation ${gen.parent_id}` : 'first generation', 'gen-meta'));
    const decision = [...gen.events].reverse().find(e => e.kind === 'decision');
    if (decision) {
      const p = el('p', null, 'quote');
      p.append(el('span', `chose ${decision.data.action}`, 'quote-act'), document.createTextNode(` “${decision.data.rationale}”`));
      card.append(p);
    }
    card.append(details('Raw events', gen.events));
    container.append(card);
  }
}

function renderMemories() {
  const container = $('memories');
  if (!current.memories.length) empty(container, 'No memories recorded yet.');
  else clear(container);
  for (const m of [...current.memories].reverse()) {
    const card = el('article', null, 'memory');
    const head = el('div', null, 'gen-head');
    head.append(el('strong', `#${m.id}`), el('span', `${m.action} → ${OUTCOME_WORD[m.outcome] || m.outcome}`, `outcome-${m.outcome}`));
    card.append(head, el('div', `generation ${m.generation_id} · ${m.world_version} · seed ${m.seed}`, 'gen-meta'),
      details('Provenance', m.evidence));
    container.append(card);
  }
  const previous = $('compare-seed').value;
  const seeds = [...new Set(current.memories.filter(m => m.world_version === 'v1').map(m => m.seed))];
  $('compare-seed').replaceChildren();
  if (!seeds.length) $('compare-seed').append(el('option', 'Make a v1 decision first'));
  for (const seed of seeds) { const option = el('option', `seed ${seed}`); option.value = seed; $('compare-seed').append(option); }
  if (seeds.map(String).includes(previous)) $('compare-seed').value = previous;
  $('compare-seed').disabled = !seeds.length || running;
  $('compare').disabled = !seeds.length || running;
  $('cells').disabled = !seeds.length || running;
}

// A two-gate strip that replays one trial: hint, then choice, then outcome.
function miniScene(trial) {
  const info = R.hintInfo(trial);
  const scene = el('div', null, 'mini');
  if (info.hint) scene.classList.add(`hint-${info.hint}`);
  if (['left', 'right'].includes(trial.action)) scene.classList.add(`choice-${trial.action}`);
  scene.classList.add(`out-${trial.outcome}`);
  for (const side of ['left', 'right']) {
    const door = el('span', side === 'left' ? 'L' : 'R', `mini-door mini-${side}`);
    if (trial.action === side) door.classList.add('chosen');
    scene.append(door);
  }
  if (info.hint) scene.append(el('span', 'hint', 'mini-hint'));
  scene.append(el('span', null, 'mini-agent'));
  scene.setAttribute('aria-hidden', 'true');
  return scene;
}
function play(scene, delay) {
  if (reduceMotion) { scene.classList.add('play'); return; }
  // Snap back to the start without animating, then run hint → walk → outcome.
  scene.classList.add('reset');
  scene.classList.remove('play');
  void scene.offsetWidth;
  scene.classList.remove('reset');
  setTimeout(() => scene.classList.add('play'), delay);
}

function trialCell(trial) {
  const cell = el('button', null, `cell outcome-${trial.outcome}`);
  cell.type = 'button';
  const info = R.hintInfo(trial);
  const scene = miniScene(trial);
  cell.append(el('span', R.SCENARIO_LABELS[trial.scenario] || trial.scenario, 'cell-scenario'),
    el('span', OUTCOME_WORD[trial.outcome] || '—', 'cell-outcome'), scene);
  const facts = el('span', null, 'cell-facts');
  facts.append(el('span', `chose ${trial.action}`));
  if (info.hint) {
    facts.append(el('span', `hint said ${info.hint}${info.correct === false ? ' (wrong)' : info.correct ? ' (right)' : ''}`,
      info.correct === false ? 'bad' : ''));
  } else facts.append(el('span', 'no inspection'));
  if (trial.assessment) facts.append(el('span', `verdict: ${trial.assessment.verdict}`));
  const calls = (trial.model_calls || []).length;
  facts.append(el('span', `${calls} call${calls === 1 ? '' : 's'}`));
  cell.append(facts);
  const why = R.lastRationale(trial);
  if (why) cell.append(el('span', `“${clip(why, 170)}”`, 'cell-quote'));
  cell.title = 'Replay this decision';
  cell.onclick = () => play(scene, 0);
  return {cell, scene};
}

function matrix(run, strategies) {
  const model = R.matrixModel(run, strategies);
  const grid = el('div', null, 'matrix');
  grid.append(el('span', '', 'matrix-corner'));
  for (const column of model.columns) grid.append(el('span', R.SCENARIO_LABELS[column], 'matrix-col'));
  const scenes = [];
  model.rows.forEach((row, r) => {
    const [name, note] = R.STRATEGY_LABELS[row.strategy] || [row.strategy, ''];
    const head = el('div', null, 'matrix-row');
    head.append(el('strong', name), el('span', note));
    grid.append(head);
    row.cells.forEach((trial, c) => {
      if (!trial) { grid.append(el('div', 'not run', 'cell missing')); return; }
      const {cell, scene} = trialCell(trial);
      grid.append(cell);
      scenes.push([scene, 150 + (r * 2 + c) * 140]);
    });
  });
  return {grid, scenes, preFix: model.preFix};
}

function runHeader(parts) {
  const head = el('div', null, 'run-head');
  parts.filter(Boolean).forEach((part, i) => head.append(el('span', part, i === 0 ? 'run-title' : '')));
  return head;
}

function renderComparisons() {
  const container = $('comparison-list');
  const runs = current.comparisons || [];
  if (!runs.length) return empty(container, 'No comparisons recorded yet.');
  clear(container);
  const animate = [];
  runs.forEach((run, i) => {
    const trials = R.trialsOf(run);
    const calls = trials.reduce((sum, t) => sum + (t.model_calls || []).length, 0);
    const seed = trials[0]?.seed ?? run.failed_attempt?.seed;
    const block = el(i === 0 ? 'div' : 'details', null, i === 0 ? 'run latest' : 'run earlier');
    const header = runHeader([i === 0 ? 'Latest run' : `Earlier run ${runs.length - i}`, seed !== undefined ? `seed ${seed}` : null,
      run.inspection_mode === 'matched' ? 'same hint for everyone' : 'optional inspection', `${calls} Muse calls`,
      run.status === 'partial' ? `incomplete: ${run.completed_trials} of ${run.planned_trials} trials` : null]);
    if (i === 0) block.append(header); else { const s = el('summary'); s.append(header); block.append(s); }
    const {grid, scenes, preFix} = matrix(run);
    if (preFix) block.append(el('p', 'Recorded before the label fix: Muse saw the “rule kept” world labelled v2.', 'caveat'));
    block.append(grid);
    if (run.failed_attempt) block.append(details('Interrupted attempt', run.failed_attempt));
    block.append(details('Raw run', run));
    container.append(block);
    if (i === 0) animate.push(...scenes);
    else scenes.forEach(([scene]) => scene.classList.add('play'));
  });
  if (!renderComparisons.done) { animate.forEach(([scene, delay]) => play(scene, delay)); renderComparisons.done = true; }
  else animate.forEach(([scene]) => scene.classList.add('play'));
}

function renderCells() {
  const capacity = current.cell_capacity;
  const reserved = current.cell_reservations;
  if (capacity && reserved) {
    $('cell-capacity').textContent = `Reserved right now: ${reserved.slots} of ${capacity.max_concurrent_cells} cells · ${reserved.calls} of ${capacity.max_calls} calls · ${reserved.output_tokens} of ${capacity.max_output_tokens} output tokens`;
  }
  const container = $('cell-list');
  const runs = current.cell_runs || [];
  if (!runs.length) return empty(container, 'No parallel runs recorded yet.');
  clear(container);
  runs.forEach((run, i) => {
    const cells = run.cells || [];
    const block = el(i === 0 ? 'div' : 'details', null, i === 0 ? 'run latest' : 'run earlier');
    const header = runHeader([i === 0 ? 'Latest parallel run' : `Earlier parallel run ${runs.length - i}`, `seed ${run.seed}`,
      cells.map(c => `${(R.STRATEGY_LABELS[c.strategy] || [c.strategy])[0]} ${c.calls} calls${c.status === 'complete' ? '' : ' (failed)'}`).join(' · '),
      run.status === 'partial' ? 'incomplete' : null]);
    if (i === 0) block.append(header); else { const s = el('summary'); s.append(header); block.append(s); }
    const {grid, scenes, preFix} = matrix(run, cells.map(c => c.strategy));
    if (preFix) block.append(el('p', 'Recorded before the label fix: Muse saw the “rule kept” world labelled v2.', 'caveat'));
    block.append(grid);
    scenes.forEach(([scene]) => scene.classList.add('play'));
    block.append(details('Raw run and reservation', run));
    container.append(block);
  });
}

async function action(button, path, data, waitText) {
  if (path !== '/api/restart') running = true;
  render(); button.disabled = true; notify(waitText);
  const timer = path === '/api/cells' ? setInterval(() => refresh().catch(() => {}), 2000) : null;
  try {
    const result = await api(path, data);
    if (result.generation) selected = result.generation.id;
    if (path === '/api/cells') {
      notify(result.status === 'complete' ? 'Both cells finished. Results saved.' : 'A cell failed. Partial results were saved and marked incomplete.', result.status !== 'complete');
    } else if (path === '/api/comparison' && result.status === 'partial') {
      notify('Comparison interrupted. Partial results were saved and marked incomplete.', true);
    } else {
      notify(path === '/api/verified-step' ? `Muse chose ${result.decision.action}. The backend recorded: ${OUTCOME_WORD[result.status] || result.status}.` : path === '/api/continue-changed' ? 'A new life in the changed world is ready.' : path === '/api/step' ? `Muse chose ${result.decision.action}. The backend recorded: ${OUTCOME_WORD[result.status] || result.status}.`
        : path === '/api/comparison' ? 'Comparison finished. Every cell is a real Muse decision.' : 'Generation ready.');
    }
    if (path === '/api/comparison') renderComparisons.done = false;
  } catch (error) { notify(error.message, true); }
  finally { if (timer) clearInterval(timer); if (path !== '/api/restart') running = false; await refresh().catch(error => notify(error.message, true)); }
}
$('start').onclick = () => {
  const seed = Number($('seed').value);
  if (!$('seed').value || !Number.isInteger(seed) || Math.abs(seed) > 1000000000) return notify('Enter an integer seed between -1000000000 and 1000000000.', true);
  action($('start'), '/api/start', {version: $('version').value, seed}, 'Starting a generation…');
};
$('step').onclick = () => action($('step'), '/api/step', {generation_id: selected}, 'Waiting for Muse…');
$('restart').onclick = () => action($('restart'), '/api/restart', {generation_id: selected}, 'Ending this generation and starting its child…');
$('continue-changed').onclick = () => action($('continue-changed'), '/api/continue-changed', {generation_id: selected}, 'Creating the linked life in the changed world…');
$('verified-step').onclick = () => action($('verified-step'), '/api/verified-step', {generation_id: selected}, 'Waiting for Muse to assess the memory and choose…');
$('compare').onclick = () => action($('compare'), '/api/comparison', {seeds: [Number($('compare-seed').value)], inspection_mode: $('inspection-mode').value}, 'Running the comparison with real Muse calls. This can take a few minutes…');
$('cells').onclick = () => action($('cells'), '/api/cells', {seed: Number($('compare-seed').value)}, 'Running both cells in parallel with real Muse calls…');

const planItems = [
  {id:'A', value:12, cpu_millis:600, memory_mib:600, time_seconds:1, cost_units:1},
  {id:'B', value:9, cpu_millis:500, memory_mib:500, time_seconds:1, cost_units:1},
  {id:'C', value:9, cpu_millis:500, memory_mib:500, time_seconds:1, cost_units:1}
];
$('plan').onclick = async () => {
  const ids = {cpu_millis:'budget-cpu', memory_mib:'budget-memory', time_seconds:'budget-time', cost_units:'budget-cost', cells:'budget-cells'};
  const budgets = {};
  for (const [key, id] of Object.entries(ids)) {
    const text = $(id).value;
    const value = Number(text);
    if (!/^\d+$/.test(text) || !Number.isSafeInteger(value) || value > 1000000000000) {
      $('plan-result').textContent = 'Enter whole-number budgets from 0 to 1,000,000,000,000.'; return;
    }
    budgets[key] = value;
  }
  $('plan').disabled = true;
  try {
    const result = await api('/api/planner', {candidates: planItems, budgets});
    const box = $('plan-result'); clear(box); box.classList.add('planner-result');
    box.append(el('strong', `Selected: ${result.selected.join(' + ') || 'none'} · declared value ${result.total_value}`));
    box.append(el('div', `Reserved: ${result.reserved.cpu_millis} millicores · ${result.reserved.memory_mib} MiB · ${result.reserved.time_seconds} s · ${result.reserved.cost_units} units · ${result.reserved.cells} cells`, 'gen-meta'));
    box.append(el('div', `${result.feasible_subsets} feasible subsets checked.`, 'hint'));
  } catch (error) { $('plan-result').textContent = error.message; }
  finally { $('plan').disabled = false; }
};
refresh().catch(error => notify(error.message, true));

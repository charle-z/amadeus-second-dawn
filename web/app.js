'use strict';
const $ = id => document.getElementById(id);
let selected = null;
let current = {generations: [], memories: [], comparisons: []};
let running = false;

function el(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined && text !== null) n.textContent = String(text);
  if (className) n.className = className;
  return n;
}
function clear(node) { node.replaceChildren(); node.classList.remove('empty'); }
function notify(text, error = false) {
  $('notice').hidden = !text;
  $('notice').textContent = text;
  $('notice').classList.toggle('error', error);
}
function details(title, value) {
  const node = el('details');
  node.append(el('summary', title), el('pre', JSON.stringify(value, null, 2)));
  return node;
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
  $('selected-title').textContent = gen ? `Generation #${gen.id} · ${gen.world_version.toUpperCase()} / seed ${gen.seed}` : 'No generation selected';
  $('selected-status').textContent = gen ? gen.status.toUpperCase() : '—';
  $('selected-status').className = `badge outcome-${gen?.status || 'none'}`;
  $('observation').textContent = gen ? `${gen.observation.scene} ${gen.observation.goal}` : 'Start a generation to see its observation and let Muse choose an action.';
  $('step').disabled = !gen || gen.status !== 'alive' || running;
  $('restart').disabled = !gen;
  $('generation-count').textContent = `${current.generations.length} GENERATIONS`;
  $('memory-count').textContent = String(current.memories.length);
  renderGenerations(); renderMemories(); renderComparisons();
}
function renderGenerations() {
  const container = $('generations'); clear(container);
  if (!current.generations.length) { container.textContent = 'No generations yet.'; container.classList.add('empty'); return; }
  for (const gen of current.generations) {
    const card = el('article', null, `gen${gen.id === selected ? ' selected' : ''}`);
    const head = el('div', null, 'gen-head');
    const btn = el('button', `#${gen.id} · ${gen.world_version.toUpperCase()} / ${gen.seed}`);
    btn.onclick = () => { selected = gen.id; render(); };
    head.append(btn, el('span', gen.status.toUpperCase(), `badge outcome-${gen.status}`));
    card.append(head, el('div', gen.parent_id ? `RESTARTED FROM #${gen.parent_id}` : 'INITIAL GENERATION', 'gen-meta'));
    for (const event of gen.events) {
      const row = el('div', null, 'event');
      row.append(el('strong', event.kind.toUpperCase() + ' '));
      if (event.kind === 'decision') row.append(document.createTextNode(`${event.data.action} · ${event.data.rationale}`));
      else if (event.kind === 'birth') row.append(document.createTextNode(event.data.scene || 'World initialized'));
      else if (event.kind === 'killed') row.append(document.createTextNode('Execution ended by restart.'));
      else row.append(document.createTextNode(event.data.result || event.kind));
      row.append(details('Evidence', event.data)); card.append(row);
    }
    container.append(card);
  }
}
function renderMemories() {
  const container = $('memories'); clear(container);
  if (!current.memories.length) { container.textContent = 'No memories recorded yet.'; container.classList.add('empty'); }
  for (const m of [...current.memories].reverse()) {
    const card = el('article', null, 'memory');
    const head = el('div', null, 'gen-head');
    head.append(el('strong', `Memory #${m.id}`), el('span', String(m.outcome).toUpperCase(), `outcome-${m.outcome}`));
    card.append(head, el('div', `GEN #${m.generation_id} / ${m.world_version.toUpperCase()} / SEED ${m.seed}`, 'gen-meta'),
      el('p', `Action: ${m.action}`), details('Provenance & evidence', m.evidence));
    container.append(card);
  }
  const previous = $('compare-seed').value;
  const seeds = [...new Set(current.memories.filter(m => m.world_version === 'v1').map(m => m.seed))];
  $('compare-seed').replaceChildren();
  if (!seeds.length) $('compare-seed').append(el('option', 'Create a V1 memory first'));
  for (const seed of seeds) { const option = el('option', seed); option.value = seed; $('compare-seed').append(option); }
  if (seeds.map(String).includes(previous)) $('compare-seed').value = previous;
  $('compare-seed').disabled = !seeds.length || running;
  $('compare').disabled = !seeds.length || running;
}
function renderComparisons() {
  const container = $('comparison-list'); clear(container);
  if (!current.comparisons.length) { container.textContent = 'No comparisons run yet.'; container.classList.add('empty'); return; }
  for (const comparison of current.comparisons) {
    const group = el('div');
    group.append(details('Summary by strategy', comparison.summary));
    if (comparison.scenario_summary) group.append(details('Stable vs shifted results', comparison.scenario_summary));
    if (comparison.limitations) group.append(details('Limitations', comparison.limitations));
    for (const trial of comparison.trials || []) {
      const row = el('div', null, 'trial'); const head = el('div', null, 'trial-head');
      head.append(el('strong', `${trial.strategy} · ${trial.scenario}`), el('span', String(trial.outcome || '—').toUpperCase(), `outcome-${trial.outcome}`));
      row.append(head, el('div', `SEED ${trial.seed} / ACTION ${trial.action ?? '—'} / COST ${trial.cost ?? '—'}`, 'sub'), details('Decision, inspection & evidence', trial));
      group.append(row);
    }
    container.append(group);
  }
}
async function action(button, path, data, waitText) {
  if (path !== '/api/restart') running = true;
  render(); button.disabled = true; notify(waitText);
  try {
    const result = await api(path, data);
    if (result.generation) selected = result.generation.id;
    notify(path === '/api/step' ? `Muse chose ${result.decision.action}; the evaluator reported ${result.status}.` : path === '/api/comparison' ? 'Comparison complete. Results are from real calls.' : 'Generation ready.');
  } catch (error) { notify(error.message, true); }
  finally { if (path !== '/api/restart') running = false; await refresh().catch(error => notify(error.message, true)); }
}
$('start').onclick = () => {
  const seed = Number($('seed').value);
  if (!$('seed').value || !Number.isInteger(seed) || Math.abs(seed) > 1000000000) return notify('Enter an integer seed between -1000000000 and 1000000000.', true);
  action($('start'), '/api/start', {version: $('version').value, seed}, 'Starting generation…');
};
$('step').onclick = () => action($('step'), '/api/step', {generation_id: selected}, 'Waiting for a real Muse decision…');
$('restart').onclick = () => action($('restart'), '/api/restart', {generation_id: selected}, 'Ending generation and restarting…');
$('compare').onclick = () => action($('compare'), '/api/comparison', {seeds: [Number($('compare-seed').value)]}, 'Running comparison with real Muse calls. This may take minutes…');
refresh().catch(error => notify(error.message, true));

'use strict';

// Standalone DOM stub: no browser, network, model calls or dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function makeElement() {
  let className = '';
  return {
    textContent: '',
    get className() { return className; },
    set className(value) { className = value; },
    classList: {
      add(...names) {
        const classes = new Set(className.split(/\s+/).filter(Boolean));
        names.forEach(name => classes.add(name));
        className = [...classes].join(' ');
      },
    },
  };
}

function setup() {
  const ids = ['world-scene', 'world-metadata', 'world-description', 'world-left', 'world-right'];
  const nodes = Object.fromEntries(ids.map(id => [id, makeElement()]));
  const context = { window: {}, document: { getElementById: id => nodes[id] || null } };
  const source = fs.readFileSync(path.join(__dirname, '..', 'web', 'world.js'), 'utf8');
  vm.runInNewContext(source, context, { filename: 'world.js' });
  const has = (id, name) => nodes[id].className.split(/\s+/).includes(name);
  return { render: context.window.renderWorld, nodes, has };
}

function generation(overrides = {}) {
  return { id: 1, world_version: 'v1', seed: 7, status: 'alive', events: [], ...overrides };
}
function decision(action) { return { kind: 'decision', data: { action } }; }

test('no generation shows an empty scene', () => {
  const { render, nodes, has } = setup();
  render(null);
  assert.equal(nodes['world-metadata'].textContent, 'NO GENERATION SELECTED');
  assert.match(nodes['world-description'].textContent, /No action has been recorded/);
  assert.equal(has('world-scene', 'world-has-generation'), false);
  assert.equal(has('world-left', 'world-door-selected'), false);
  assert.equal(has('world-right', 'world-door-selected'), false);
});

test('version and seed alone never select or reveal a gate', () => {
  const { render, nodes, has } = setup();
  for (const world_version of ['v1', 'v2']) {
    for (const seed of [0, 7, -19]) {
      render(generation({ world_version, seed }));
      assert.equal(nodes['world-metadata'].textContent, `GENERATION #1 / ${world_version.toUpperCase()} / SEED ${seed}`);
      assert.match(nodes['world-description'].textContent, /No action has been recorded/);
      assert.equal(has('world-left', 'world-door-selected'), false);
      assert.equal(has('world-right', 'world-door-selected'), false);
      assert.equal(has('world-scene', 'world-action-left'), false);
      assert.equal(has('world-scene', 'world-action-right'), false);
    }
  }
});

test('a recorded decision and backend outcome drive the view independently', () => {
  const { render, nodes, has } = setup();
  render(generation({ status: 'dead', events: [decision('left')] }));
  assert.match(nodes['world-description'].textContent, /Muse chose left.*backend recorded death/);
  assert.equal(has('world-scene', 'world-state-dead'), true);
  assert.equal(has('world-left', 'world-door-selected'), true);
  assert.equal(has('world-right', 'world-door-selected'), false);

  // Same action and seed, different recorded outcome: the UI must not compute it.
  render(generation({ world_version: 'v2', status: 'won', events: [decision('left')] }));
  assert.match(nodes['world-description'].textContent, /Muse chose left.*backend recorded a win/);
  assert.equal(has('world-scene', 'world-state-won'), true);
  assert.equal(has('world-left', 'world-door-selected'), true);
  assert.equal(has('world-right', 'world-door-selected'), false);
});

test('changing generation clears old action, outcome and selected door', () => {
  const { render, nodes, has } = setup();
  render(generation({ status: 'dead', events: [decision('left')] }));
  render(generation({ id: 2, status: 'alive' }));
  assert.match(nodes['world-metadata'].textContent, /GENERATION #2/);
  assert.match(nodes['world-description'].textContent, /No action.*Alive/);
  assert.equal(has('world-left', 'world-door-selected'), false);
  assert.equal(has('world-scene', 'world-state-dead'), false);
  assert.equal(has('world-scene', 'world-action-left'), false);
  render(generation({ id: 2, status: 'won', events: [decision('right')] }));
  assert.equal(has('world-left', 'world-door-selected'), false);
  assert.equal(has('world-right', 'world-door-selected'), true);
  assert.match(nodes['world-description'].textContent, /Muse chose right.*backend recorded a win/);
  render(null);
  assert.equal(has('world-right', 'world-door-selected'), false);
  assert.equal(has('world-scene', 'world-state-won'), false);
});

test('killed and malformed or absent decisions are represented without guessing', () => {
  const { render, nodes, has } = setup();
  render(generation({ status: 'killed', events: [{ kind: 'killed', data: {} }] }));
  assert.match(nodes['world-description'].textContent, /No action.*killed by restart/);
  assert.equal(has('world-scene', 'world-state-killed'), true);
  for (const events of [[decision('inspect')], [{ kind: 'decision', data: {} }], null]) {
    render(generation({ status: 'dead', events }));
    assert.match(nodes['world-description'].textContent, /No action has been recorded/);
    assert.equal(has('world-left', 'world-door-selected'), false);
    assert.equal(has('world-right', 'world-door-selected'), false);
  }
});

test('the latest recorded decision is displayed', () => {
  const { render, has } = setup();
  render(generation({ status: 'won', events: [decision('left'), { kind: 'birth' }, decision('right')] }));
  assert.equal(has('world-left', 'world-door-selected'), false);
  assert.equal(has('world-right', 'world-door-selected'), true);
});

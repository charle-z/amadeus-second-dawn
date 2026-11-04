'use strict';

// Render only the selected generation and its recorded decision; never infer a safe gate.
window.renderWorld = function renderWorld(generation) {
  const scene = document.getElementById('world-scene');
  const metadata = document.getElementById('world-metadata');
  const status = document.getElementById('world-description');
  const left = document.getElementById('world-left');
  const right = document.getElementById('world-right');
  if (!scene || !metadata || !status || !left || !right) return;

  scene.className = 'world-scene';
  left.className = 'world-door';
  right.className = 'world-door';
  if (!generation) {
    metadata.textContent = 'NO GENERATION SELECTED';
    status.textContent = 'Start a generation to observe the world. No action has been recorded.';
    return;
  }

  const state = ['alive', 'dead', 'won', 'killed'].includes(generation.status)
    ? generation.status : 'unknown';
  const events = Array.isArray(generation.events) ? generation.events : [];
  const decision = [...events].reverse().find(event => event && event.kind === 'decision');
  const action = decision && decision.data && ['left', 'right'].includes(decision.data.action)
    ? decision.data.action : null;
  const version = String(generation.world_version || 'unknown').toUpperCase();
  metadata.textContent = `GENERATION #${generation.id} / ${version} / SEED ${generation.seed}`;
  const descriptions = {
    alive: 'Alive and awaiting a recorded decision.',
    dead: 'The backend recorded death.',
    won: 'The backend recorded a win.',
    killed: 'The generation was killed by restart.',
    unknown: 'The generation status is unknown.'
  };
  const description = (action ? `Muse chose ${action}. ` : 'No action has been recorded. ') + descriptions[state];
  if (status.textContent !== description) status.textContent = description;
  scene.classList.add('world-has-generation', `world-state-${state}`);
  if (action) {
    scene.classList.add(`world-action-${action}`);
    (action === 'left' ? left : right).classList.add('world-door-selected');
  }
};

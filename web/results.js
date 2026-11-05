'use strict';

// Pure views of recorded trials. Nothing here knows the safe gate: whether a
// hint was right is read back from the action and the backend's outcome.
(function (root) {
  const STRATEGY_LABELS = {
    NO_MEMORY: ['No memory', 'sees nothing from the past'],
    NAIVE_MEMORY: ['Naive', 'gets every memory'],
    VERIFIED_MEMORY: ['Verified', 'judges each memory first'],
  };
  const SCENARIO_LABELS = { stable: 'Rule kept', shifted: 'Rule flipped' };
  const GATES = ['left', 'right'];

  function hintInfo(trial) {
    const hint = trial && trial.inspection && GATES.includes(trial.inspection.hint) ? trial.inspection.hint : null;
    if (!hint || !GATES.includes(trial.action) || !['won', 'dead'].includes(trial.outcome)) {
      return { hint, followed: null, correct: null };
    }
    const followed = trial.action === hint;
    // Following a correct hint survives; ignoring a correct hint dies.
    const correct = followed ? trial.outcome === 'won' : trial.outcome === 'dead';
    return { hint, followed, correct };
  }

  function lastRationale(trial) {
    const calls = Array.isArray(trial && trial.model_calls) ? trial.model_calls : [];
    for (let i = calls.length - 1; i >= 0; i -= 1) {
      const response = calls[i] && calls[i].response;
      if (response && typeof response.rationale === 'string' && 'action' in response) return response.rationale;
    }
    return typeof (trial && trial.rationale) === 'string' ? trial.rationale : '';
  }

  // Before the label fix, the "rule kept" world was shown to Muse as v2.
  function labelPreFix(trial) {
    return Boolean(trial && trial.scenario === 'stable' && trial.world_version === 'v2');
  }

  function trialsOf(run) {
    if (!run) return [];
    if (Array.isArray(run.trials)) return run.trials;
    if (Array.isArray(run.cells)) return run.cells.flatMap(cell => (Array.isArray(cell.trials) ? cell.trials : []));
    return [];
  }

  function matrixModel(run, strategies) {
    const trials = trialsOf(run);
    const rows = strategies || Object.keys(STRATEGY_LABELS).filter(s => trials.some(t => t.strategy === s));
    return {
      columns: Object.keys(SCENARIO_LABELS),
      rows: rows.map(strategy => ({
        strategy,
        cells: Object.keys(SCENARIO_LABELS).map(scenario =>
          trials.find(t => t.strategy === strategy && t.scenario === scenario) || null),
      })),
      preFix: trials.some(labelPreFix),
    };
  }

  function tally(runs) {
    const result = { trials: 0, survived: 0, inspected: 0, followed: 0, hintWrong: 0, verdicts: {} };
    for (const run of runs || []) {
      for (const trial of trialsOf(run)) {
        if (!['won', 'dead'].includes(trial.outcome)) continue;
        result.trials += 1;
        if (trial.outcome === 'won') result.survived += 1;
        const info = hintInfo(trial);
        if (info.hint) {
          result.inspected += 1;
          if (info.followed) result.followed += 1;
          if (info.correct === false) result.hintWrong += 1;
        }
        const verdict = trial.assessment && trial.assessment.verdict;
        if (typeof verdict === 'string') result.verdicts[verdict] = (result.verdicts[verdict] || 0) + 1;
      }
    }
    return result;
  }

  root.AmadeusResults = { STRATEGY_LABELS, SCENARIO_LABELS, hintInfo, lastRationale, labelPreFix, trialsOf, matrixModel, tally };
})(typeof window !== 'undefined' ? window : globalThis);

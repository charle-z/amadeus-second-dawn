"""Two real worker threads with process-local, atomic resource reservations.

Reservations bound concurrent admitted cells and declared model output budgets;
they do not enforce physical CPU/RAM, provider billing or an account-wide cap.
All entry points must share the same coordinator for its process-local guarantee.

Proof: under one lock the coordinator accepts a pair only if the resulting
number n of leases is <= 2. Each lease reserves (4, 4 * output_cap), hence
the aggregate reservation is (4n, 4n * output_cap) <= (8, 8 * output_cap).
Lease release only reduces n. The per-cell wrapper rejects call attempt five.
"""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from .arena import MAX_COMPLETION_TOKENS, SCENARIOS, _trial

CALLS_PER_CELL = 4
OUTPUT_PER_CELL = CALLS_PER_CELL * MAX_COMPLETION_TOKENS
MAX_SLOTS = 2
MAX_CALLS = MAX_SLOTS * CALLS_PER_CELL
MAX_OUTPUT = MAX_SLOTS * OUTPUT_PER_CELL
STRATEGIES = ('NAIVE_MEMORY', 'VERIFIED_MEMORY')


class AdmissionError(RuntimeError):
    """The complete pair does not fit; no work was submitted."""


class BudgetError(RuntimeError):
    """A cell attempted to exceed its call reservation."""


class CallBudget:
    """Count attempts before each adapter call, including failed attempts."""
    def __init__(self, decide):
        self.decide = decide
        self.calls = 0
        self.last_usage = None

    def __call__(self, stage, context):
        if self.calls >= CALLS_PER_CELL:
            raise BudgetError('Cell call budget exhausted')
        self.calls += 1
        self.last_usage = None
        try:
            return self.decide(stage, context)
        finally:
            self.last_usage = copy.deepcopy(getattr(self.decide, 'last_usage', None))


def _freeze(memories, seed):
    if type(seed) is not int or not -(2**63) <= seed < 2**63:
        raise ValueError('Invalid seed')
    if not isinstance(memories, list):
        raise ValueError('Expected a list of recorded memories')
    selected = [m for m in memories if isinstance(m, dict) and m.get('world_version') == 'v1'
                and m.get('seed') == seed and type(m.get('id')) is int
                and m.get('action') in ('left', 'right') and m.get('outcome') in ('won', 'dead')
                and isinstance(m.get('evidence'), dict)]
    if not selected:
        raise ValueError('The seed needs at least one recorded V1 memory')
    selected = copy.deepcopy(sorted(selected, key=lambda m: m['id'])[-4:])
    try:
        encoded = json.dumps(selected, ensure_ascii=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('Memories must be JSON serializable') from exc
    if len(encoded) > 32768:
        raise ValueError('Training memories exceed the input size limit')
    return selected


class CellCoordinator:
    """One instance must be shared by all cell requests in the server process."""
    def __init__(self):
        self._lock = threading.Lock()
        self._leases = set()
        self._sequence = 0

    def snapshot(self):
        with self._lock:
            slots = len(self._leases)
            return {'slots': slots, 'calls': slots * CALLS_PER_CELL,
                    'output_tokens': slots * OUTPUT_PER_CELL}

    def _admit_pair(self):
        with self._lock:
            existing = len(self._leases)
            requested = len(STRATEGIES)
            if (existing + requested > MAX_SLOTS or
                    (existing + requested) * CALLS_PER_CELL > MAX_CALLS or
                    (existing + requested) * OUTPUT_PER_CELL > MAX_OUTPUT):
                raise AdmissionError('Not enough capacity for both cells')
            leases = []
            for _ in STRATEGIES:
                self._sequence += 1
                self._leases.add(self._sequence)
                leases.append(self._sequence)
            return leases

    def _release(self, lease):
        with self._lock:
            # Idempotent release makes a failed submit and worker cleanup safe.
            self._leases.discard(lease)

    def _cell(self, lease, strategy, seed, memories, agent_factory):
        limited = None
        trials = []
        try:
            limited = CallBudget(agent_factory(strategy))
            for scenario in SCENARIOS:
                trials.append(_trial(seed, scenario, strategy, copy.deepcopy(memories), limited, inspection_mode='optional'))
            return {'strategy': strategy, 'status': 'complete', 'calls': limited.calls, 'trials': trials}
        except Exception as exc:
            return {'strategy': strategy, 'status': 'failed', 'calls': limited.calls if limited else 0,
                    'trials': trials, 'error_type': type(exc).__name__,
                    'failed_usage': copy.deepcopy(limited.last_usage) if limited else None,
                    'error': 'Cell failed; its completed trials, if any, are partial.'}
        finally:
            self._release(lease)

    def _gated_cell(self, gate, lease, strategy, seed, memories, agent_factory):
        # submit() can enqueue work and then raise while starting a thread.
        # Such a queued job must not start after its reservation is released.
        gate['ready'].wait()
        if not gate['accepted']:
            self._release(lease)
            return None
        return self._cell(lease, strategy, seed, memories, agent_factory)

    def run(self, memories, seed, agent_factory):
        """Run paired strategies on real threads. `agent_factory(strategy)` returns one agent.

        No retries. The adapter is responsible for using MAX_COMPLETION_TOKENS;
        the arena Muse adapter uses that shared value. No model calls are made
        before admission. A failed cell is reported, never counted as complete.
        """
        frozen = _freeze(memories, seed)
        leases = self._admit_pair()
        futures = []
        cells = []
        try:
            with ThreadPoolExecutor(max_workers=MAX_SLOTS, thread_name_prefix='amadeus-cell') as executor:
                for i, strategy in enumerate(STRATEGIES):
                    gate = {'ready': threading.Event(), 'accepted': False}
                    try:
                        try:
                            future = executor.submit(self._gated_cell, gate, leases[i], strategy, seed, frozen, agent_factory)
                            futures.append(future)
                            gate['accepted'] = True
                        finally:
                            gate['ready'].set()
                    except Exception as exc:
                        for j in range(i, len(STRATEGIES)):
                            self._release(leases[j])
                            cells.append({'strategy': STRATEGIES[j], 'status': 'failed', 'calls': 0,
                                          'trials': [], 'error_type': type(exc).__name__,
                                          'error': 'Cell was not submitted.'})
                        break
                for future in futures:
                    cells.append(future.result())
        except BaseException:
            # Submitted jobs release themselves only after they actually finish.
            for lease in leases[len(futures):]:
                self._release(lease)
            raise
        cells.sort(key=lambda x: STRATEGIES.index(x['strategy']))
        return {'status': 'complete' if all(c['status'] == 'complete' for c in cells) else 'partial',
                'seed': seed, 'inspection_mode': 'optional', 'cells': cells,
                'reservation': {'max_concurrent_cells': MAX_SLOTS, 'max_calls': MAX_CALLS,
                                'max_output_tokens': MAX_OUTPUT, 'per_cell_calls': CALLS_PER_CELL,
                                'per_call_max_completion_tokens': MAX_COMPLETION_TOKENS},
                'limitations': ['Reservations are logical admission limits within one process.',
                                'They do not impose CPU or RAM quotas or a global spending cap.',
                                'Output token reservations depend on the adapter and provider honoring the shared cap.',
                                'Input tokens, training calls, repeated runs and billing are not capped by this reservation.']}

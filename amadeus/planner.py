"""Exact, bounded admission planning using declared, additive reservations.

`cpu_millis` means reserved millicores, not CPU milliseconds. `memory_mib`
means reserved MiB. `time_seconds` is the *sum* of reserved seconds, not
parallel wall-clock makespan. `cost_units` and `value` are non-negative integer
units chosen by the caller; value is an additive expected-value estimate, not
an observed outcome. Integers avoid floating point rounding and ambiguous ties.

This planner does not allocate or enforce resources, impose CPU/RAM quotas,
guarantee duration or spending, or make expected values true. Admission must be
performed atomically against current capacity by a separate coordinator.
"""

MAX_CANDIDATES = 16
MAX_METRIC = 10**12
RESOURCES = ('cpu_millis', 'memory_mib', 'time_seconds', 'cost_units')
_CANDIDATE_KEYS = frozenset((*RESOURCES, 'id', 'value'))
_BUDGET_KEYS = frozenset((*RESOURCES, 'cells'))


def _nonnegative_integer(value):
    if type(value) is not int or not 0 <= value <= MAX_METRIC:
        raise ValueError('Resources and values must be bounded non-negative integers')


def select_exact(candidates, budgets):
    """Return the optimal feasible subset (maximum 16 candidates).

    Each candidate has exactly id, value and the four named resources; each
    consumes one cell. Budgets additionally contain the cells bound. Ties use
    fewer cells, then lexicographically smaller sorted IDs. Input order does not
    affect the answer. Search considers feasible subsets exactly; no heuristic.
    """
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        raise ValueError(f'Candidates must be a list with at most {MAX_CANDIDATES} items')
    if type(budgets) is not dict or set(budgets) != _BUDGET_KEYS:
        raise ValueError('Invalid budget fields')
    for v in budgets.values():
        _nonnegative_integer(v)
    seen = set()
    for candidate in candidates:
        if type(candidate) is not dict or set(candidate) != _CANDIDATE_KEYS:
            raise ValueError('Invalid candidate fields')
        name = candidate['id']
        if type(name) is not str or not 1 <= len(name) <= 80 or name != name.strip() or name in seen:
            raise ValueError('Candidate IDs must be unique nonempty trimmed strings of at most 80 characters')
        seen.add(name)
        for key in (*RESOURCES, 'value'):
            _nonnegative_integer(candidate[key])

    ordered = sorted(candidates, key=lambda candidate: candidate['id'])
    remaining = [budgets[key] for key in RESOURCES]
    selected = []
    best_ids = ()
    best_value = -1
    feasible_subsets = 0

    def search(index, value):
        nonlocal best_ids, best_value, feasible_subsets
        if index == len(ordered):
            feasible_subsets += 1
            ids = tuple(selected)
            if (value > best_value or
                    (value == best_value and (len(ids), ids) < (len(best_ids), best_ids))):
                best_value, best_ids = value, ids
            return
        search(index + 1, value)
        candidate = ordered[index]
        amounts = [candidate[key] for key in RESOURCES]
        if len(selected) >= budgets['cells'] or any(amount > available for amount, available in zip(amounts, remaining)):
            return
        for i, amount in enumerate(amounts):
            remaining[i] -= amount
        selected.append(candidate['id'])
        search(index + 1, value + candidate['value'])
        selected.pop()
        for i, amount in enumerate(amounts):
            remaining[i] += amount

    search(0, 0)
    chosen = set(best_ids)
    reserved = {key: sum(c[key] for c in ordered if c['id'] in chosen) for key in RESOURCES}
    reserved['cells'] = len(best_ids)
    return {'selected': list(best_ids), 'total_value': best_value, 'reserved': reserved,
            'feasible_subsets': feasible_subsets, 'method': 'exact_enumeration',
            'limitations': ['Declared values are estimates, not measured outcomes.',
                            'Reservations do not enforce CPU, memory, runtime or spending.',
                            'Reserved time is an additive budget, not parallel makespan.',
                            'Planning must be followed by atomic admission against current capacity.']}

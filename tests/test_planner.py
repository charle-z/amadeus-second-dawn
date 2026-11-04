import itertools
import random
import unittest

from amadeus.planner import select_exact, MAX_CANDIDATES

RESOURCES = ('cpu_millis', 'memory_mib', 'time_seconds', 'cost_units')


def item(id, value, cpu=0, memory=0, time=0, cost=0):
    return dict(id=id, value=value, cpu_millis=cpu, memory_mib=memory,
                time_seconds=time, cost_units=cost)


def bounds(cpu=100, memory=100, time=100, cost=100, cells=10):
    return dict(cpu_millis=cpu, memory_mib=memory, time_seconds=time,
                cost_units=cost, cells=cells)


def oracle(candidates, budget):
    options = []
    for size in range(len(candidates) + 1):
        for subset in itertools.combinations(candidates, size):
            if size > budget['cells'] or any(sum(x[k] for x in subset) > budget[k] for k in RESOURCES):
                continue
            ids = tuple(sorted(x['id'] for x in subset))
            options.append((-sum(x['value'] for x in subset), size, ids))
    return min(options)


class PlannerTests(unittest.TestCase):
    def test_finds_combination_greedy_by_value_misses(self):
        candidates = [item('A', 12, cpu=6), item('B', 9, cpu=5), item('C', 9, cpu=5)]
        result = select_exact(candidates, bounds(cpu=10, cells=2))
        self.assertEqual(result['selected'], ['B', 'C'])
        self.assertEqual(result['total_value'], 18)
        self.assertEqual(result['reserved']['cpu_millis'], 10)
        self.assertEqual(result['reserved']['cells'], 2)

    def test_matches_independent_brute_force_across_small_cases(self):
        rng = random.Random(2718)
        for _ in range(100):
            candidates = [item(chr(65+i), rng.randrange(12), *(rng.randrange(5) for _ in RESOURCES))
                          for i in range(rng.randrange(9))]
            budget = bounds(*(rng.randrange(10) for _ in RESOURCES), cells=rng.randrange(7))
            result = select_exact(candidates, budget)
            expected = oracle(candidates, budget)
            self.assertEqual((-result['total_value'], len(result['selected']), tuple(result['selected'])), expected)
            chosen = [x for x in candidates if x['id'] in result['selected']]
            for key in RESOURCES:
                self.assertEqual(result['reserved'][key], sum(x[key] for x in chosen))
                self.assertLessEqual(result['reserved'][key], budget[key])

    def test_ties_minimize_count_then_use_sorted_ids_independent_of_input_order(self):
        candidates = [item('B', 5, cpu=5), item('A', 5, cpu=5), item('C', 10, cpu=10), item('D', 10, cpu=10)]
        expected = ['C']
        for order in (candidates, list(reversed(candidates)), [candidates[1], candidates[3], candidates[0], candidates[2]]):
            self.assertEqual(select_exact(order, bounds(cpu=10, cells=2))['selected'], expected)
        self.assertEqual(select_exact([item('z', 0)], bounds())['selected'], [])

    def test_each_budget_is_enforced_and_empty_is_feasible(self):
        candidate = item('x', 10, 1, 1, 1, 1)
        for k in (*RESOURCES, 'cells'):
            budget = bounds()
            budget[k] = 0
            result = select_exact([candidate], budget)
            self.assertEqual(result['selected'], [])
            self.assertEqual(result['total_value'], 0)
        self.assertEqual(select_exact([], bounds())['feasible_subsets'], 1)

    def test_strict_validation(self):
        valid = item('a', 1)
        for bad in (True, -1, 1.0, '1', None):
            bad_item = dict(valid, value=bad)
            with self.subTest(value=bad), self.assertRaises(ValueError):
                select_exact([bad_item], bounds())
            bad_budget = dict(bounds(), cpu_millis=bad)
            with self.subTest(budget=bad), self.assertRaises(ValueError):
                select_exact([valid], bad_budget)
        for candidates in ([valid, valid], [dict(valid, id='')], [dict(valid, id=' a')], [dict(valid, extra=1)],
                           [item(str(i), 1) for i in range(MAX_CANDIDATES + 1)]):
            with self.subTest(candidates=len(candidates)), self.assertRaises(ValueError):
                select_exact(candidates, bounds())
        with self.assertRaises(ValueError): select_exact([valid], dict(bounds(), extra=1))
        with self.assertRaises(ValueError): select_exact(None, bounds())

    def test_sixteen_candidates_are_allowed_and_input_is_unchanged(self):
        candidates = [item(str(i), 1) for i in range(MAX_CANDIDATES)]
        before = [candidate.copy() for candidate in candidates]
        result = select_exact(candidates, bounds(cells=MAX_CANDIDATES))
        self.assertEqual(result['feasible_subsets'], 2 ** MAX_CANDIDATES)
        self.assertEqual(result['total_value'], MAX_CANDIDATES)
        self.assertEqual(candidates, before)


if __name__ == '__main__': unittest.main()

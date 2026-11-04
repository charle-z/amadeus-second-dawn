import threading
import time
import unittest
from unittest.mock import patch

from amadeus.cells import CellCoordinator, AdmissionError, CallBudget, BudgetError
from amadeus.arena import MAX_COMPLETION_TOKENS


MEMORIES = [{'id': 11, 'generation_id': 9, 'world_version': 'v1', 'seed': 7,
             'action': 'left', 'outcome': 'dead', 'evidence': {'result': 'dead'}}]


def answer(stage, context):
    if stage == 'assess':
        return {'memory_id': 11, 'evidence_id': 'inspection-1', 'verdict': 'uncertain', 'rationale': 'uncertain'}
    return {'action': 'left', 'rationale': 'choice'}


class CellTests(unittest.TestCase):
    def test_both_cells_really_overlap_and_other_pair_is_rejected(self):
        coordinator = CellCoordinator()
        barrier = threading.Barrier(3)
        release = threading.Event()
        entries = []
        lock = threading.Lock()
        def factory(strategy):
            first = True
            def decide(stage, context):
                nonlocal first
                if first:
                    first = False
                    with lock:
                        entries.append((strategy, context['observation']['seed'], context['memories']))
                    barrier.wait(timeout=5)
                    release.wait(timeout=5)
                return answer(stage, context)
            return decide
        result = []
        worker = threading.Thread(target=lambda: result.append(coordinator.run(MEMORIES, 7, factory)))
        worker.start()
        try:
            barrier.wait(timeout=5)
            self.assertEqual(coordinator.snapshot(), {'slots': 2, 'calls': 8, 'output_tokens': 8 * MAX_COMPLETION_TOKENS})
            with self.assertRaises(AdmissionError):
                coordinator.run(MEMORIES, 7, factory)
            self.assertEqual(len(entries), 2)
        finally:
            release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0]['status'], 'complete')
        self.assertEqual(result[0]['inspection_mode'], 'optional')
        self.assertTrue(all(t['inspection_mode'] == 'optional' for cell in result[0]['cells'] for t in cell['trials']))
        self.assertEqual({x['strategy'] for x in result[0]['cells']}, {'NAIVE_MEMORY', 'VERIFIED_MEMORY'})
        self.assertEqual({x[1] for x in entries}, {7})
        self.assertTrue(all(x[2] == MEMORIES for x in entries))
        self.assertEqual(coordinator.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})

    def test_failure_is_explicit_and_all_reservations_release(self):
        c = CellCoordinator()
        def factory(strategy):
            if strategy == 'NAIVE_MEMORY':
                def bad(stage, context): raise RuntimeError('example failure')
                return bad
            return answer
        result = c.run(MEMORIES, 7, factory)
        self.assertEqual(result['status'], 'partial')
        naive = next(x for x in result['cells'] if x['strategy'] == 'NAIVE_MEMORY')
        verified = next(x for x in result['cells'] if x['strategy'] == 'VERIFIED_MEMORY')
        self.assertEqual(naive['status'], 'failed')
        self.assertEqual(naive['calls'], 1)
        self.assertEqual(verified['status'], 'complete')
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})

    def test_pair_rejected_if_only_one_slot_is_free(self):
        c = CellCoordinator()
        blocked = threading.Event()
        release = threading.Event()
        result = []
        def factory(strategy):
            if strategy == 'NAIVE_MEMORY':
                def bad(stage, context): raise RuntimeError('cell failed')
                return bad
            def waiting(stage, context):
                blocked.set()
                release.wait(timeout=5)
                return answer(stage, context)
            return waiting
        worker = threading.Thread(target=lambda: result.append(c.run(MEMORIES, 7, factory)))
        worker.start()
        try:
            self.assertTrue(blocked.wait(5))
            deadline = time.monotonic() + 5
            while c.snapshot()['slots'] != 1 and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertEqual(c.snapshot()['slots'], 1)
            attempted = []
            with self.assertRaises(AdmissionError):
                c.run(MEMORIES, 7, lambda strategy: attempted.append(strategy))
            self.assertEqual(attempted, [])
            self.assertEqual(c.snapshot()['slots'], 1)
        finally:
            release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0]['status'], 'partial')
        self.assertEqual(c.snapshot()['slots'], 0)

    def test_duplicate_release_does_not_release_another_cell(self):
        c = CellCoordinator()
        first, second = c._admit_pair()
        c._release(first)
        c._release(first)
        self.assertEqual(c.snapshot()['slots'], 1)
        c._release(second)
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})

    def test_fifth_attempt_is_rejected_before_model_call(self):
        seen = []
        def decide(stage, context):
            seen.append(stage)
            return {}
        limited = CallBudget(decide)
        for _ in range(4): limited('act', {})
        with self.assertRaises(BudgetError): limited('act', {})
        self.assertEqual(len(seen), 4)
        self.assertEqual(limited.calls, 4)

    def test_call_budget_keeps_failed_usage_and_clears_stale_usage(self):
        class Agent:
            last_usage = None
            calls = 0
            def __call__(self, stage, context):
                self.calls += 1
                if self.calls == 1:
                    self.last_usage = {"prompt_tokens": 1, "completion_tokens": 2}
                    return {}
                self.last_usage = ({"prompt_tokens": 10, "completion_tokens": 1024}
                                   if self.calls == 2 else None)
                raise RuntimeError("incomplete")
        limited = CallBudget(Agent())
        limited("act", {})
        with self.assertRaises(RuntimeError): limited("act", {})
        self.assertEqual(limited.last_usage, {"prompt_tokens": 10, "completion_tokens": 1024})
        with self.assertRaises(RuntimeError): limited("act", {})
        self.assertIsNone(limited.last_usage)
        self.assertEqual(limited.calls, 3)

    def test_no_work_without_valid_training_memory(self):
        c = CellCoordinator()
        entered = []
        with self.assertRaises(ValueError): c.run([], 7, lambda strategy: entered.append(strategy))
        self.assertEqual(entered, [])
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})

    def test_releases_unsubmitted_reservation_when_submit_fails(self):
        c = CellCoordinator()
        from concurrent.futures import ThreadPoolExecutor
        original_submit = ThreadPoolExecutor.submit
        count = 0
        def fail_second(executor, *args, **kwargs):
            nonlocal count
            count += 1
            if count == 2: raise RuntimeError('submit failed')
            return original_submit(executor, *args, **kwargs)
        with patch('amadeus.cells.ThreadPoolExecutor.submit', fail_second):
            result = c.run(MEMORIES, 7, lambda strategy: answer)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['cells']), 2)
        self.assertEqual(sum(x['status'] == 'failed' for x in result['cells']), 1)
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})
        # Subsequent admissions still have the full budget; no negative counters.
        self.assertEqual(c.run(MEMORIES, 7, lambda strategy: answer)['status'], 'complete')
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})

    def test_submit_that_enqueues_then_raises_never_starts_unadmitted_cell(self):
        c = CellCoordinator()
        from concurrent.futures import ThreadPoolExecutor
        original_submit = ThreadPoolExecutor.submit
        n = 0
        entered = []
        lock = threading.Lock()
        def enqueue_then_fail(executor, *args, **kwargs):
            nonlocal n
            n += 1
            future = original_submit(executor, *args, **kwargs)
            if n == 2: raise RuntimeError('failed after enqueue')
            return future
        def factory(strategy):
            with lock: entered.append(strategy)
            return answer
        with patch('amadeus.cells.ThreadPoolExecutor.submit', enqueue_then_fail):
            result = c.run(MEMORIES, 7, factory)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(entered, ['NAIVE_MEMORY'])
        self.assertEqual(c.snapshot(), {'slots': 0, 'calls': 0, 'output_tokens': 0})


if __name__ == '__main__': unittest.main()

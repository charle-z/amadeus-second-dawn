import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from amadeus.server import make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.tmp.name) / 'test.sqlite3', port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        payload = None if data is None else json.dumps(data).encode()
        req = Request(self.base + path, data=payload, headers=headers or {'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read())

    def test_full_lifecycle_and_memory(self):
        start = self.request('/api/start', {'version': 'v1', 'seed': 1})['generation']
        with patch('amadeus.server.MuseAgent', return_value=lambda obs, memories: {'action': 'left', 'rationale': 'test'}):
            result = self.request('/api/step', {'generation_id': start['id']})
        self.assertIn(result['status'], ('won', 'dead'))
        restarted = self.request('/api/restart', {'generation_id': start['id']})['generation']
        state = self.request('/api/state')
        self.assertEqual(restarted['parent_id'], start['id'])
        self.assertEqual(len(state['memories']), 1)
        self.assertEqual(len(state['generations']), 2)
        self.assertEqual([e['kind'] for e in state['generations'][1]['events']][0], 'birth')

    def test_second_life_http_persists_realistic_verified_trace(self):
        original = self.request('/api/start', {'version': 'v1', 'seed': 7})['generation']
        with patch('amadeus.server.MuseAgent', return_value=lambda obs, mem: {'action': 'left', 'rationale': 'test only'}):
            first = self.request('/api/step', {'generation_id': original['id']})
        child = self.request('/api/continue-changed', {'generation_id': original['id']})['generation']
        self.assertEqual((child['parent_id'], child['world_version'], child['seed']), (original['id'], 'v2', 7))
        def decide(stage, context):
            if stage == 'assess':
                return {'memory_id': first['memory']['id'], 'evidence_id': 'inspection-1',
                        'verdict': 'uncertain', 'rationale': 'test only'}
            self.assertEqual(context['memories'], [])
            return {'action': 'right', 'rationale': 'test only'}
        with patch('amadeus.arena.MuseArenaAgent', return_value=decide):
            result = self.request('/api/verified-step', {'generation_id': child['id']})
        self.assertEqual(result['trial']['assessment']['verdict'], 'uncertain')
        self.assertEqual(result['trial']['outcome'], result['status'])
        saved = self.request('/api/state')
        actual = next(g for g in saved['generations'] if g['id'] == child['id'])
        self.assertEqual(next(e for e in actual['events'] if e['kind'] == 'verified_trial')['data'], result['trial'])
        self.assertEqual(len(saved['memories']), 2)

    def test_second_life_rejects_bad_state_and_sanitizes_model_failure(self):
        first = self.request('/api/start', {'version': 'v1', 'seed': 7})['generation']
        with self.assertRaises(HTTPError) as error:
            self.request('/api/continue-changed', {'generation_id': first['id']})
        self.assertEqual(error.exception.code, 400)
        with patch('amadeus.server.MuseAgent', return_value=lambda obs, mem: {'action': 'left', 'rationale': 'test only'}):
            self.request('/api/step', {'generation_id': first['id']})
        child = self.request('/api/continue-changed', {'generation_id': first['id']})['generation']
        def fail(stage, context):
            raise RuntimeError('PRIVATE PROVIDER DETAILS')
        with patch('amadeus.arena.MuseArenaAgent', return_value=fail):
            with self.assertRaises(HTTPError) as error:
                self.request('/api/verified-step', {'generation_id': child['id']})
        self.assertEqual(error.exception.code, 502)
        self.assertNotIn('PRIVATE', error.exception.read().decode())
        saved = self.request('/api/state')
        self.assertEqual(next(g for g in saved['generations'] if g['id'] == child['id'])['status'], 'alive')
        self.assertEqual(len(saved['memories']), 1)
        self.server.busy.acquire()
        try:
            with patch('amadeus.arena.MuseArenaAgent') as model:
                with self.assertRaises(HTTPError) as error:
                    self.request('/api/verified-step', {'generation_id': child['id']})
                self.assertEqual(error.exception.code, 400)
                model.assert_not_called()
        finally:
            self.server.busy.release()

    def test_bad_requests_rejected(self):
        for path, data in [('/api/start', {'version': 'v3', 'seed': 1}),
                           ('/api/start', {'version': 'v1', 'seed': True}),
                           ('/api/step', {'generation_id': -1}),
                           ('/api/comparison', {'seeds': [1,2,3]})]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as ctx:
                self.request(path, data)
            self.assertEqual(ctx.exception.code, 400)

    def test_rejects_cross_origin_and_serves_ui(self):
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/start', {'version': 'v1', 'seed': 1},
                         {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(ctx.exception.code, 403)
        with urlopen(self.base + '/', timeout=5) as response:
            self.assertIn(b'AMADEUS', response.read())

    def test_every_ui_file_is_utf8_and_every_script_is_served(self):
        web = Path(__file__).resolve().parent.parent / 'web'
        for path in web.iterdir():
            path.read_bytes().decode('utf-8')
        index = (web / 'index.html').read_text(encoding='utf-8')
        for script in ('/world.js', '/results.js', '/app.js'):
            self.assertIn(f'src="{script}"', index)
            with urlopen(self.base + script, timeout=5) as response:
                self.assertIn('javascript', response.headers['Content-Type'])
                response.read().decode('utf-8')

    def test_model_failure_is_reported_and_does_not_write_a_decision(self):
        start = self.request('/api/start', {'version': 'v1', 'seed': 1})['generation']
        with patch('amadeus.server.MuseAgent', side_effect=RuntimeError('Model unavailable')):
            with self.assertRaises(HTTPError) as ctx:
                self.request('/api/step', {'generation_id': start['id']})
        self.assertEqual(ctx.exception.code, 502)
        state = self.request('/api/state')
        self.assertEqual(state['generations'][0]['status'], 'alive')
        self.assertEqual(state['memories'], [])

    def test_comparison_persists_only_when_complete(self):
        result = {'trials': [{'strategy': 'NO_MEMORY', 'outcome': 'dead'}],
                  'summary': [], 'limitations': ['test data']}
        with patch('amadeus.arena.MuseArenaAgent', return_value=object()), \
             patch('amadeus.arena.run_comparison', return_value=result):
            self.assertEqual(self.request('/api/comparison', {'seeds': [7]}), result)
        with patch('amadeus.arena.MuseArenaAgent', return_value=object()), \
             patch('amadeus.arena.run_comparison', side_effect=RuntimeError('API failed')):
            with self.assertRaises(HTTPError) as ctx:
                self.request('/api/comparison', {'seeds': [7]})
        self.assertEqual(ctx.exception.code, 502)
        self.assertEqual(self.request('/api/state')['comparisons'], [result])

    def test_interrupted_comparison_persists_partial_evidence(self):
        from amadeus.arena import ComparisonInterrupted
        partial = {'status': 'partial', 'inspection_mode': 'matched',
                   'completed_trials': 1, 'planned_trials': 6,
                   'trials': [{'strategy': 'NO_MEMORY', 'outcome': 'dead'}],
                   'failed_attempt': {'stage': 'action', 'usage': None}}
        with patch('amadeus.arena.MuseArenaAgent', return_value=object()), \
             patch('amadeus.arena.run_comparison', side_effect=ComparisonInterrupted(partial)):
            self.assertEqual(self.request('/api/comparison', {'seeds': [7], 'inspection_mode': 'matched'}), partial)
        self.assertEqual(self.request('/api/state')['comparisons'], [partial])

    def test_comparison_accepts_matched_inspection_and_persists_mode(self):
        result = {"inspection_mode": "matched", "trials": [], "summary": []}
        with patch("amadeus.arena.MuseArenaAgent", return_value=object()), \
             patch("amadeus.arena.run_comparison", return_value=result) as run:
            self.assertEqual(self.request("/api/comparison", {"seeds": [7], "inspection_mode": "matched"}), result)
        self.assertEqual(run.call_args.kwargs["inspection_mode"], "matched")
        self.assertEqual(self.request("/api/state")["comparisons"], [result])
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/comparison", {"seeds": [7], "inspection_mode": "invalid"})
        self.assertEqual(ctx.exception.code, 400)

    def test_cells_persist_complete_and_partial_with_status(self):
        complete = {'status': 'complete', 'seed': 7, 'cells': [], 'reservation': {}}
        partial = {'status': 'partial', 'seed': 7, 'cells': [{'status': 'failed', 'error_type': 'RuntimeError'}]}
        with patch.object(self.server.cells, 'run', side_effect=[complete, partial]):
            self.assertEqual(self.request('/api/cells', {'seed': 7}), complete)
            self.assertEqual(self.request('/api/cells', {'seed': 7}), partial)
        state = self.request('/api/state')
        self.assertEqual(state['cell_runs'], [partial, complete])
        self.assertEqual(state['cell_capacity']['max_concurrent_cells'], 2)

    def test_cells_share_busy_gate_and_validate_input(self):
        for data in ({'seed': True}, {'seed': 1, 'unexpected': True}):
            with self.assertRaises(HTTPError) as ctx:
                self.request('/api/cells', data)
            self.assertEqual(ctx.exception.code, 400)
        self.server.busy.acquire()
        try:
            with patch.object(self.server.cells, 'run') as run:
                with self.assertRaises(HTTPError) as ctx:
                    self.request('/api/cells', {'seed': 7})
                self.assertEqual(ctx.exception.code, 400)
                run.assert_not_called()
        finally:
            self.server.busy.release()

    def test_cells_http_runs_real_arena_with_test_only_adapter(self):
        generation = self.request('/api/start', {'version': 'v1', 'seed': 7})['generation']
        with patch('amadeus.server.MuseAgent', return_value=lambda obs, mem: {'action': 'left', 'rationale': 'test'}):
            self.request('/api/step', {'generation_id': generation['id']})
        def decide(stage, context):
            if stage == 'assess':
                return {'memory_id': context['memories'][0]['id'], 'evidence_id': 'inspection-1',
                        'verdict': 'uncertain', 'rationale': 'test observation'}
            return {'action': 'left', 'rationale': 'test choice'}
        with patch('amadeus.arena.MuseArenaAgent', side_effect=lambda: decide):
            result = self.request('/api/cells', {'seed': 7})
        self.assertEqual(result['status'], 'complete')
        self.assertEqual({c['strategy'] for c in result['cells']}, {'NAIVE_MEMORY', 'VERIFIED_MEMORY'})
        self.assertTrue(all(len(c['trials']) == 2 for c in result['cells']))
        self.assertEqual(self.request('/api/state')['cell_runs'], [result])

    def test_planner_http_selects_exactly_without_model_or_cell_work(self):
        resources = {'cpu_millis': 10, 'memory_mib': 20, 'time_seconds': 20, 'cost_units': 20}
        def candidate(name, value, cpu):
            return {'id': name, 'value': value, 'cpu_millis': cpu, 'memory_mib': 0,
                    'time_seconds': 0, 'cost_units': 0}
        body = {'budgets': {**resources, 'cells': 2},
                'candidates': [candidate('A', 12, 6), candidate('B', 9, 5), candidate('C', 9, 5)]}
        before = self.request('/api/state')
        self.server.busy.acquire()
        try:
            with patch('amadeus.server.MuseAgent', side_effect=AssertionError('unexpected model call')), \
                 patch('amadeus.arena.MuseArenaAgent', side_effect=AssertionError('unexpected model call')), \
                 patch.object(self.server.cells, 'run', side_effect=AssertionError('unexpected cell run')):
                result = self.request('/api/planner', body)
        finally:
            self.server.busy.release()
        self.assertEqual(result['selected'], ['B', 'C'])
        self.assertEqual(result['total_value'], 18)
        self.assertEqual(result['reserved']['cpu_millis'], 10)
        self.assertEqual(self.request('/api/state'), before)

    def test_planner_http_rejects_invalid_input_and_cross_origin(self):
        budgets = {'cpu_millis': 1, 'memory_mib': 1, 'time_seconds': 1, 'cost_units': 1, 'cells': 1}
        candidate = {'id': 'a', 'value': 1, 'cpu_millis': 1, 'memory_mib': 1, 'time_seconds': 1, 'cost_units': 1}
        for data in ({'candidates': [candidate], 'budgets': {**budgets, 'cells': True}},
                     {'candidates': [candidate, candidate], 'budgets': budgets},
                     {'candidates': [candidate], 'budgets': budgets, 'extra': True},
                     {'candidates': [candidate] * 17, 'budgets': budgets}):
            with self.subTest(data=data), self.assertRaises(HTTPError) as ctx:
                self.request('/api/planner', data)
            self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(HTTPError) as ctx:
            self.request('/api/planner', {'candidates': [], 'budgets': budgets},
                         {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == '__main__':
    unittest.main()

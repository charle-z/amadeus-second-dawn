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


if __name__ == '__main__':
    unittest.main()

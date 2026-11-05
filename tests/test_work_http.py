import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from amadeus.server import make_server

class WorkHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root=Path(self.tmp.name); self.workspace=root/'workspace'; self.workspace.mkdir()
        (self.workspace/'notes.md').write_text('actual evidence', encoding='utf-8')
        self.server=make_server(root/'test.sqlite',port=0); self.server.work_root=str(self.workspace)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True); self.worker.start()
        self.base='http://127.0.0.1:%d' % self.server.server_port
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(); self.tmp.cleanup()
    def request(self, path, data=None, headers=None):
        req=Request(self.base+path, data=json.dumps(data).encode() if data is not None else None,
                    headers=headers or {'Content-Type':'application/json'})
        with urlopen(req, timeout=5) as response: return json.load(response)
    def test_real_endpoints_with_mocked_model(self):
        task=self.request('/api/work/start', {'goal':'inspect','paths':['notes.md']})
        (self.workspace/'notes.md').write_text('new evidence',encoding='utf-8')
        with patch('amadeus.work.MuseWorkAgent', return_value=lambda context: {'summary':'changed','findings':[{'path':'notes.md','quote':'new evidence','assessment':'Updated.'}],'next_step':'Review it.'}):
            result=self.request('/api/work/resume', {'task_id':task['task']['id']})
        self.assertEqual(result['changes'][0]['status'],'changed')
        state=self.request('/api/state'); self.assertTrue(state['work_available'])
        self.assertEqual(state['work_tasks'][0]['last_result'],result)
    def test_delete_requires_same_origin_and_respects_busy_gate(self):
        generation=self.request('/api/start', {'version':'v1','seed':7})['generation']
        with patch('amadeus.server.MuseAgent', return_value=lambda obs, memories: {'action':'left','rationale':'test only'}):
            self.request('/api/step', {'generation_id':generation['id']})
        before=self.request('/api/state')
        task=self.request('/api/work/start', {'goal':'inspect','paths':['notes.md']})['task']
        with self.assertRaises(HTTPError) as error:
            self.request('/api/work/delete', {'task_id':task['id']}, {'Content-Type':'application/json','Origin':'https://evil.example'})
        self.assertEqual(error.exception.code,403)
        self.server.busy.acquire()
        try:
            with self.assertRaises(HTTPError) as error:
                self.request('/api/work/delete', {'task_id':task['id']})
            self.assertEqual(error.exception.code,400)
            self.assertEqual(len(self.request('/api/state')['work_tasks']),1)
        finally: self.server.busy.release()
        result=self.request('/api/work/delete', {'task_id':task['id']})
        self.assertEqual(result, {'task_id':task['id'],'deleted':True})
        after=self.request('/api/state')
        self.assertEqual(after['work_tasks'],[])
        self.assertEqual(after['generations'], before['generations'])
        self.assertEqual(after['memories'], before['memories'])

    def test_work_rejects_cross_origin_and_traversal(self):
        with self.assertRaises(HTTPError) as e:
            self.request('/api/work/start', {'goal':'inspect','paths':['../x.md']})
        self.assertEqual(e.exception.code,400)
        with self.assertRaises(HTTPError) as e:
            self.request('/api/work/start', {'goal':'inspect','paths':['notes.md']}, {'Content-Type':'application/json','Origin':'https://evil.example'})
        self.assertEqual(e.exception.code,403)

    def test_inspection_is_local_and_rejects_cross_origin(self):
        task = self.request('/api/work/start', {'goal': 'inspect', 'paths': ['notes.md']})['task']
        (self.workspace/'notes.md').write_text('updated locally', encoding='utf-8')
        with patch('amadeus.work.MuseWorkAgent', side_effect=AssertionError('model must not be used')):
            result = self.request('/api/work/inspect', {'task_id': task['id']})
        self.assertEqual(result['review_status'], 'no_review')
        self.assertEqual(result['changes'][0]['status'], 'changed')
        with self.assertRaises(HTTPError) as error:
            self.request('/api/work/inspect', {'task_id': task['id']},
                         {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(error.exception.code, 403)

    def test_checkpoint_is_persisted_locally_and_rejects_cross_origin(self):
        task = self.request('/api/work/start', {'goal': 'continue', 'paths': ['notes.md']})['task']
        payload = {'task_id': task['id'], 'completed': 'Reviewed spec', 'attempted': '', 'next_step': 'Check tests'}
        with patch('amadeus.work.MuseWorkAgent', side_effect=AssertionError('model must not be used')):
            saved = self.request('/api/work/checkpoint', payload)
        self.assertEqual(saved['checkpoint']['next_step'], 'Check tests')
        self.assertEqual(self.request('/api/state')['work_tasks'][0]['checkpoint']['completed'], 'Reviewed spec')
        with self.assertRaises(HTTPError) as error:
            self.request('/api/work/checkpoint', payload,
                         {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(error.exception.code, 403)

    def test_handoff_is_local_and_rejects_cross_origin(self):
        task = self.request('/api/work/start', {'goal': 'continue', 'paths': ['notes.md']})['task']
        with patch('amadeus.work.MuseWorkAgent', side_effect=AssertionError('model must not be used')):
            result = self.request('/api/work/handoff', {'task_id': task['id']})
        self.assertEqual(result['format'], 'amadeus-handoff-v1')
        self.assertIsNone(result['review'])
        with self.assertRaises(HTTPError) as error:
            self.request('/api/work/handoff', {'task_id': task['id']},
                         {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})
        self.assertEqual(error.exception.code, 403)

if __name__ == '__main__': unittest.main()

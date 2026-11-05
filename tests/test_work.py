import tempfile
import unittest
from pathlib import Path
from amadeus.core import Experiment
from amadeus.work import WorkManager

class WorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'; self.root.mkdir()
        self.db = Path(self.tmp.name) / 'work.sqlite'
        self.e = Experiment(self.db)
        self.work = WorkManager(self.e.db, self.root)
        (self.root / 'notes.md').write_text('version one\nkeep this\n', encoding='utf-8')
    def tearDown(self):
        self.e.close(); self.tmp.cleanup()
    def test_persists_and_detects_real_change(self):
        first = self.work.start('Review this change', ['notes.md'])
        (self.root / 'notes.md').write_text('version two\nkeep this\n', encoding='utf-8')
        self.e.close(); self.e = Experiment(self.db); self.work = WorkManager(self.e.db, self.root)
        def fake(context):
            self.assertEqual(context['changes'][0]['status'], 'changed')
            return {'summary':'changed', 'findings':[{'path':'notes.md','quote':'version two','assessment':'Updated.'}], 'next_step':'Review update.'}
        result = self.work.resume(first['task']['id'], fake)
        self.assertEqual(result['changes'][0]['status'], 'changed')
        self.assertIn('version two', result['changes'][0]['diff'])
        self.assertEqual(self.work.list_tasks()[0]['last_result'], result)
    def test_refuses_escape_and_secret_filenames_and_content(self):
        for path in ('../outside.md', '.env', '/absolute.md', 'secrets.md', 'notes.md:stream'):
            with self.subTest(path=path), self.assertRaises(ValueError): self.work.start('goal', [path])
        (self.root / 'notes.md').write_text('MODEL_API_KEY=super-secret-value-should-not-be-read', encoding='utf-8')
        with self.assertRaises(ValueError) as error: self.work.start('goal', ['notes.md'])
        self.assertNotIn('super-secret', str(error.exception))
        self.assertEqual(self.work.list_tasks(), [])
    def test_rejects_invalid_model_quote_and_no_result(self):
        task = self.work.start('goal', ['notes.md'])['task']
        with self.assertRaises(ValueError):
            self.work.resume(task['id'], lambda _: {'summary':'x','findings':[{'path':'notes.md','quote':'fabricated','assessment':'x'}], 'next_step':'x'})
        self.assertIsNone(self.work.list_tasks()[0]['last_result'])
    def test_previous_analysis_is_rechecked_against_current_file(self):
        task = self.work.start('goal', ['notes.md'])['task']
        initial = {'summary':'original', 'findings':[], 'next_step':'Continue.'}
        self.work.resume(task['id'], lambda _: initial)
        (self.root / 'notes.md').write_text('different evidence', encoding='utf-8')
        def check(context):
            self.assertEqual(context['previous_analysis'], initial)
            self.assertEqual(context['changes'][0]['status'], 'changed')
            self.assertEqual(context['changes'][0]['since_last_status'], 'changed')
            return {'summary':'revised', 'findings':[], 'next_step':'Review differences.'}
        result = self.work.resume(task['id'], check)
        self.assertEqual(result['previous_analysis'], initial)
    def test_json_secrets_and_goal_are_rejected(self):
        with self.assertRaises(ValueError):
            self.work.start('password = super-long-password', ['notes.md'])
        for name in ('api_key', 'access_token'):
            (self.root / 'notes.md').write_text('{"' + name + '":"example-long-key-123456"}', encoding='utf-8')
            with self.assertRaises(ValueError): self.work.start('goal', ['notes.md'])
    def test_deleted_file_and_concurrent_change(self):
        task = self.work.start('goal', ['notes.md'])['task']
        (self.root / 'notes.md').unlink()
        result = self.work.resume(task['id'], lambda c: {'summary':'missing','findings':[], 'next_step':'Restore the file.'})
        self.assertEqual(result['changes'][0]['status'], 'missing')
        (self.root / 'notes.md').write_text('back', encoding='utf-8')
        def race(context):
            (self.root / 'notes.md').write_text('changed while model running', encoding='utf-8')
            return {'summary':'old', 'findings':[], 'next_step':'review'}
        with self.assertRaises(ValueError): self.work.resume(task['id'], race)
        self.assertEqual(self.work.list_tasks()[0]['last_result'], result)
    def test_symlink_cannot_escape_workspace(self):
        external = Path(self.tmp.name) / 'outside.md'; external.write_text('outside', encoding='utf-8')
        link = self.root / 'linked.md'
        try: link.symlink_to(external)
        except OSError: self.skipTest('symlinks unavailable')
        with self.assertRaises(ValueError): self.work.start('goal', ['linked.md'])
    def test_python_syntax_checked_independently(self):
        (self.root / 'broken.py').write_text('def missing(:\n', encoding='utf-8')
        task = self.work.start('check syntax', ['broken.py'])['task']
        def decide(context):
            self.assertEqual(context['diagnostics'][0]['status'], 'fail')
            return {'summary':'Syntax error detected.', 'findings':[], 'next_step':'Fix syntax.'}
        result = self.work.resume(task['id'], decide)
        self.assertEqual(result['diagnostics'][0]['check'], 'python-syntax')
        self.assertEqual(result['diagnostics'][0]['status'], 'fail')

    def test_workspace_identity_is_enforced(self):
        task = self.work.start('goal', ['notes.md'])['task']
        other = Path(self.tmp.name) / 'other'; other.mkdir()
        manager = WorkManager(self.e.db, other)
        self.assertEqual(manager.list_tasks(), [])
        with self.assertRaises(ValueError): manager.resume(task['id'], lambda _: None)

    def test_missing_workspace_is_disabled(self):
        with self.assertRaises(ValueError): WorkManager(self.e.db, None).start('goal', ['notes.md'])

if __name__ == '__main__': unittest.main()

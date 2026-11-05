import tempfile
import unittest
from pathlib import Path

from amadeus.core import Experiment
from amadeus.work import WorkManager


class LocalInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'
        self.root.mkdir()
        (self.root / 'notes.py').write_text('value = 1\n', encoding='utf-8')
        self.exp = Experiment(Path(self.tmp.name) / 'db.sqlite')
        self.work = WorkManager(self.exp.db, self.root)
        self.task_id = self.work.start('Continue work', ['notes.py'])['task']['id']

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def test_inspects_current_files_without_creating_a_model_review(self):
        (self.root / 'notes.py').write_text('def broken(:\n', encoding='utf-8')
        result = self.work.inspect(self.task_id)
        self.assertEqual(result['review_status'], 'no_review')
        self.assertEqual(result['changes'][0]['status'], 'changed')
        self.assertEqual(result['diagnostics'][0]['status'], 'fail')
        self.assertNotIn('analysis', result)
        self.assertIsNone(self.work.list_tasks()[0]['last_result'])
        self.assertEqual(self.exp.db.execute('SELECT COUNT(*) FROM work_reviews').fetchone()[0], 0)

    def test_reports_changed_and_missing_files_since_last_review(self):
        review = self.work.resume(self.task_id, lambda _: {
            'summary': 'review', 'findings': [], 'next_step': 'Check work.'})
        self.exp.close()
        self.exp = Experiment(Path(self.tmp.name) / 'db.sqlite')
        self.work = WorkManager(self.exp.db, self.root)
        unchanged = self.work.inspect(self.task_id)
        self.assertEqual(unchanged['review_status'], 'unchanged')
        self.assertEqual(unchanged['review_id'], self.work.list_tasks()[0]['review_history'][0]['id'])
        (self.root / 'notes.py').write_text('value = 2\n', encoding='utf-8')
        changed = self.work.inspect(self.task_id)
        self.assertEqual(changed['review_status'], 'changed')
        self.assertEqual(changed['changes'][0]['since_last_status'], 'changed')
        (self.root / 'notes.py').unlink()
        missing = self.work.inspect(self.task_id)
        self.assertEqual(missing['review_status'], 'changed')
        self.assertEqual(missing['changes'][0]['status'], 'missing')
        self.assertEqual(self.work.list_tasks()[0]['last_result'], review)
        self.assertEqual(self.exp.db.execute('SELECT COUNT(*) FROM work_reviews').fetchone()[0], 1)

    def test_workspace_scope_and_secret_filter_are_enforced(self):
        other = self.root.parent / 'other'
        other.mkdir()
        with self.assertRaises(ValueError):
            WorkManager(self.exp.db, other).inspect(self.task_id)
        (self.root / 'notes.py').write_text('api_key = "sensitive-example-value"', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.work.inspect(self.task_id)

    def test_file_size_limit_supports_medium_files_but_remains_bounded(self):
        file = self.root / 'medium.md'
        file.write_text('x' * 32768, encoding='utf-8')
        task = self.work.start('Inspect medium file', ['medium.md'])['task']
        self.assertEqual(self.work.inspect(task['id'])['changes'][0]['status'], 'unchanged')
        file.write_text('x' * 32769, encoding='utf-8')
        with self.assertRaises(ValueError):
            self.work.inspect(task['id'])


if __name__ == '__main__':
    unittest.main()

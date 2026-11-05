import tempfile
import unittest
from pathlib import Path

from amadeus.core import Experiment
from amadeus.work import WorkManager


class WorkCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'
        self.root.mkdir()
        (self.root / 'notes.md').write_text('current evidence', encoding='utf-8')
        self.db = Path(self.tmp.name) / 'work.sqlite'
        self.exp = Experiment(self.db)
        self.work = WorkManager(self.exp.db, self.root)
        self.task_id = self.work.start('Finish the work', ['notes.md'])['task']['id']

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def test_checkpoint_survives_restart_and_is_included_in_review(self):
        saved = self.work.save_checkpoint(self.task_id, 'Read the spec', 'Tried the first approach', 'Check the tests')
        self.assertEqual(saved['checkpoint']['revision'], 1)
        self.exp.close()
        self.exp = Experiment(self.db)
        self.work = WorkManager(self.exp.db, self.root)
        checkpoint = self.work.list_tasks()[0]['checkpoint']
        self.assertEqual(checkpoint['completed'], 'Read the spec')
        self.assertEqual(checkpoint['attempted'], 'Tried the first approach')
        self.assertEqual(checkpoint['next_step'], 'Check the tests')
        def decide(context):
            self.assertEqual(context['checkpoint']['next_step'], 'Check the tests')
            return {'summary': 'reviewed', 'findings': [], 'next_step': 'Continue.'}
        review = self.work.resume(self.task_id, decide)
        self.assertEqual(review['checkpoint_revision'], 1)
        self.assertEqual(self.work.inspect(self.task_id)['checkpoint_status'], 'unchanged')
        self.work.save_checkpoint(self.task_id, 'Done', '', 'Next')
        self.assertEqual(self.work.inspect(self.task_id)['checkpoint_status'], 'changed')

    def test_checkpoint_change_during_review_rejects_stale_result(self):
        self.work.save_checkpoint(self.task_id, '', '', 'First')
        def decide(context):
            self.work.save_checkpoint(self.task_id, '', '', 'Second')
            return {'summary': 'stale', 'findings': [], 'next_step': 'Continue.'}
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            self.work.resume(self.task_id, decide)
        self.assertIsNone(self.work.list_tasks()[0]['last_result'])

    def test_checkpoint_rejects_secrets_long_input_and_other_workspace(self):
        for text in ('x' * 1001, 'api_key = "example-secret-credential"'):
            with self.assertRaises(ValueError):
                self.work.save_checkpoint(self.task_id, text, '', '')
        other = self.root.parent / 'other'
        other.mkdir()
        with self.assertRaises(ValueError):
            WorkManager(self.exp.db, other).save_checkpoint(self.task_id, '', '', '')
        self.assertIsNone(self.work.list_tasks()[0]['checkpoint'])

    def test_deletion_removes_checkpoint(self):
        self.work.save_checkpoint(self.task_id, 'Done', '', '')
        self.work.delete(self.task_id)
        self.assertEqual(self.exp.db.execute('SELECT COUNT(*) FROM work_checkpoints').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()

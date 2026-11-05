import sqlite3
import tempfile
import unittest
from pathlib import Path

from amadeus.core import Experiment
from amadeus.work import WorkManager


class CheckpointHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'
        self.root.mkdir()
        (self.root / 'notes.md').write_text('evidence', encoding='utf-8')
        self.db_path = Path(self.tmp.name) / 'work.sqlite'
        self.exp = Experiment(self.db_path)
        self.work = WorkManager(self.exp.db, self.root)
        self.id = self.work.start('Resume work', ['notes.md'])['task']['id']

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def test_versions_survive_restart_and_noop_does_not_create_history(self):
        self.work.save_checkpoint(self.id, 'First', 'Blocked', 'Investigate')
        self.work.save_checkpoint(self.id, 'First', 'Blocked', 'Investigate')
        self.work.save_checkpoint(self.id, 'Second', 'Unblocked', 'Test')
        self.exp.close()
        self.exp = Experiment(self.db_path)
        self.work = WorkManager(self.exp.db, self.root)
        history = self.work.list_tasks()[0]['checkpoint_history']
        self.assertEqual([h['revision'] for h in history], [2, 1])
        self.assertEqual(history[0]['next_step'], 'Test')
        self.assertEqual(history[1]['attempted'], 'Blocked')
        self.assertTrue(all(h['updated_at'] for h in history))

    def test_migration_keeps_only_existing_latest_note_and_is_idempotent(self):
        self.work.save_checkpoint(self.id, 'Old', '', '')
        self.work.save_checkpoint(self.id, 'Most recent', '', '')
        self.exp.db.execute('DROP TABLE work_checkpoint_history')
        self.exp.db.commit()
        WorkManager(self.exp.db, self.root)
        migrated = WorkManager(self.exp.db, self.root).list_tasks()[0]['checkpoint_history']
        self.assertEqual([(h['revision'], h['completed']) for h in migrated], [(2, 'Most recent')])

    def test_history_is_bounded_in_ui_and_deleted_with_task(self):
        for i in range(12):
            self.work.save_checkpoint(self.id, f'Completed {i}', '', '')
        self.assertEqual([h['revision'] for h in self.work.list_tasks()[0]['checkpoint_history']], list(range(12, 2, -1)))
        self.work.delete(self.id)
        self.assertEqual(self.exp.db.execute('SELECT count(*) FROM work_checkpoint_history').fetchone()[0], 0)

    def test_workspace_cannot_read_another_workspaces_history(self):
        self.work.save_checkpoint(self.id, 'Private progress', '', '')
        other = self.root.parent / 'other'
        other.mkdir()
        self.assertEqual(WorkManager(self.exp.db, other).list_tasks(), [])

    def test_history_write_failure_rolls_back_the_latest_checkpoint(self):
        self.work.save_checkpoint(self.id, 'First', '', '')
        self.exp.db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON work_checkpoint_history WHEN NEW.revision > 1 BEGIN SELECT RAISE(ABORT, 'history failure'); END")
        self.exp.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.work.save_checkpoint(self.id, 'Second', '', '')
        current = self.work.list_tasks()[0]
        self.assertEqual(current['checkpoint']['completed'], 'First')
        self.assertEqual([h['revision'] for h in current['checkpoint_history']], [1])


if __name__ == '__main__':
    unittest.main()

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from amadeus.core import Experiment
from amadeus.work import WorkManager


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / 'workspace'; self.root.mkdir()
        (self.root / 'notes.md').write_text('v1 evidence', encoding='utf-8')
        self.path = self.base / 'test.sqlite'
        self.exp = Experiment(self.path)
        self.work = WorkManager(self.exp.db, self.root)
        self.fake = lambda _: {'summary':'review', 'findings':[], 'next_step':'inspect'}

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def reopen(self):
        self.exp.close()
        self.exp = Experiment(self.path)
        self.work = WorkManager(self.exp.db, self.root)

    def test_revisions_persist_latest_first_and_model_context_only_last(self):
        task = self.work.start('goal', ['notes.md'])['task']
        first = self.work.resume(task['id'], self.fake)
        (self.root / 'notes.md').write_text('v2 evidence', encoding='utf-8')
        def second_decision(context):
            self.assertEqual(context['previous_analysis'], first['analysis'])
            self.assertNotIn('review_history', context)
            return {'summary':'second', 'findings':[], 'next_step':'verify'}
        second = self.work.resume(task['id'], second_decision)
        self.reopen()
        loaded = self.work.list_tasks()[0]
        self.assertEqual(loaded['last_result'], second)
        self.assertEqual([r['result'] for r in loaded['review_history']], [second, first])
        self.assertTrue(all(r['recorded_at'] and r['origin']=='recorded' for r in loaded['review_history']))

    def test_history_is_bounded_and_delete_cascades_only_target(self):
        first=self.work.start('first', ['notes.md'])['task']
        second=self.work.start('second', ['notes.md'])['task']
        for _ in range(7): self.work.resume(first['id'], self.fake)
        self.work.resume(second['id'], self.fake)
        self.assertEqual(len(next(x for x in self.work.list_tasks() if x['id']==first['id'])['review_history']), 5)
        self.assertEqual(self.exp.db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.work.delete(first['id']); self.reopen()
        self.assertEqual(self.exp.db.execute('SELECT COUNT(*) FROM work_reviews WHERE task_id=?', (first['id'],)).fetchone()[0], 0)
        self.assertEqual(self.exp.db.execute('SELECT COUNT(*) FROM work_reviews WHERE task_id=?', (second['id'],)).fetchone()[0], 1)

    def test_legacy_backfill_is_undated_and_idempotent(self):
        task=self.work.start('goal', ['notes.md'])['task']
        result=self.work.resume(task['id'], self.fake)
        self.exp.db.execute('DROP TABLE work_reviews'); self.exp.db.commit()
        self.reopen()
        self.reopen()
        history=self.work.list_tasks()[0]['review_history']
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]['origin'], history[0]['recorded_at'], history[0]['result']), ('legacy', None, result))

    def test_concurrent_legacy_migration_has_no_duplicates(self):
        task=self.work.start('goal', ['notes.md'])['task']
        self.work.resume(task['id'], self.fake)
        self.exp.db.execute('DROP TABLE work_reviews'); self.exp.db.commit()
        barrier = threading.Barrier(2); errors=[]
        def worker():
            connection = sqlite3.connect(self.path, timeout=5); connection.row_factory = sqlite3.Row
            try:
                barrier.wait(timeout=5); WorkManager(connection, self.root)
            except Exception as exc: errors.append(type(exc).__name__)
            finally: connection.close()
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.reopen()
        self.assertEqual(len(self.work.list_tasks()[0]['review_history']), 1)

    def test_delete_cannot_affect_history_in_another_workspace(self):
        local=self.work.start('local', ['notes.md'])['task']
        self.work.resume(local['id'], self.fake)
        other=self.base / 'other'; other.mkdir()
        (other / 'notes.md').write_text('other evidence', encoding='utf-8')
        other_manager=WorkManager(self.exp.db, other)
        foreign=other_manager.start('other', ['notes.md'])['task']
        other_manager.resume(foreign['id'], self.fake)
        with self.assertRaises(ValueError): self.work.delete(foreign['id'])
        self.work.delete(local['id'])
        self.reopen()
        other_manager=WorkManager(self.exp.db, other)
        self.assertEqual(other_manager.list_tasks()[0]['id'], foreign['id'])
        self.assertEqual(len(other_manager.list_tasks()[0]['review_history']), 1)

    def test_insert_failure_rolls_back_last_result_and_history(self):
        task=self.work.start('goal', ['notes.md'])['task']
        first=self.work.resume(task['id'], self.fake)
        self.exp.db.execute("CREATE TRIGGER block_reviews BEFORE INSERT ON work_reviews BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        self.exp.db.commit()
        with self.assertRaises(sqlite3.IntegrityError): self.work.resume(task['id'], self.fake)
        self.reopen()
        loaded=self.work.list_tasks()[0]
        self.assertEqual(loaded['last_result'], first)
        self.assertEqual(len(loaded['review_history']), 1)

if __name__=='__main__': unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amadeus.core import Experiment
from amadeus import work as work_module
from amadeus.work import WorkManager


class WorkHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'workspace'
        self.root.mkdir()
        (self.root / 'app.py').write_text('value = 1\n', encoding='utf-8')
        (self.root / 'notes.md').write_text('original evidence\n', encoding='utf-8')
        self.exp = Experiment(Path(self.tmp.name) / 'work.sqlite')
        self.work = WorkManager(self.exp.db, self.root)
        self.id = self.work.start('Finish the task', ['app.py', 'notes.md'])['task']['id']

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def test_builds_local_packet_without_review_or_model(self):
        self.work.save_checkpoint(self.id, 'Read spec', 'Blocked on tests', 'Fix test')
        (self.root / 'app.py').write_text('def broken(:\n', encoding='utf-8')
        with patch('amadeus.work.MuseWorkAgent', side_effect=AssertionError('must not call model')):
            packet = self.work.handoff(self.id)
        self.assertEqual(packet['objective']['goal'], 'Finish the task')
        self.assertEqual(packet['checkpoint']['next_step'], 'Fix test')
        self.assertIsNone(packet['review'])
        self.assertEqual(self.work.inspect(self.id)['finding_evidence'], [])
        self.assertEqual(packet['files'][0]['status'], 'changed')
        self.assertEqual(packet['diagnostics'][0]['status'], 'fail')
        self.assertNotIn('diff', packet['files'][0])
        self.assertNotIn('def broken', str(packet))
        self.assertEqual(self.exp.db.execute('SELECT count(*) FROM work_reviews').fetchone()[0], 0)

    def test_validates_each_quote_against_current_files_and_marks_context_changes(self):
        self.work.resume(self.id, lambda _: {'summary': 'Earlier analysis', 'next_step': 'Check', 'findings': [
            {'path': 'app.py', 'quote': 'value = 1', 'assessment': 'Existing value'},
            {'path': 'notes.md', 'quote': 'original evidence', 'assessment': 'Existing note'},
        ]})
        self.work.save_checkpoint(self.id, 'New context', '', '')
        (self.root / 'app.py').write_text('value = 1\nother = 2\n', encoding='utf-8')
        (self.root / 'notes.md').write_text('new evidence\n', encoding='utf-8')
        packet = self.work.handoff(self.id)
        self.assertEqual(packet['review']['files_status'], 'changed')
        self.assertEqual(packet['review']['checkpoint_status'], 'changed')
        self.assertEqual([f['evidence_status'] for f in packet['review']['findings']], ['quote_present_file_changed', 'quote_missing'])
        self.assertEqual([f['evidence_status'] for f in self.work.inspect(self.id)['finding_evidence']], ['quote_present_file_changed', 'quote_missing'])
        (self.root / 'notes.md').unlink()
        self.assertEqual(self.work.handoff(self.id)['review']['findings'][1]['evidence_status'], 'file_missing')

    def test_respects_workspace_and_rejects_secret_new_content(self):
        other = self.root.parent / 'other'
        other.mkdir()
        with self.assertRaises(ValueError):
            WorkManager(self.exp.db, other).handoff(self.id)
        (self.root / 'app.py').write_text('api_key = "some-secret-value"', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.work.handoff(self.id)

    def test_rejects_a_checkpoint_changed_while_building_packet(self):
        self.work.resume(self.id, lambda _: {'summary': 'Review', 'next_step': 'Inspect', 'findings': [
            {'path': 'app.py', 'quote': 'value = 1', 'assessment': 'Value'}]})
        original = work_module._finding_evidence
        def update_notes(*args):
            result = original(*args)
            self.work.save_checkpoint(self.id, 'Changed during handoff', '', '')
            return result
        with patch('amadeus.work._finding_evidence', side_effect=update_notes):
            with self.assertRaisesRegex(ValueError, 'changed during handoff'):
                self.work.handoff(self.id)

    def test_unchanged_file_marks_only_literal_quote_as_present(self):
        self.work.resume(self.id, lambda _: {'summary': 'Review', 'next_step': 'Inspect', 'findings': [
            {'path': 'app.py', 'quote': 'value = 1', 'assessment': 'Value'}]})
        packet = self.work.handoff(self.id)
        self.assertEqual(packet['review']['findings'][0]['evidence_status'], 'quote_present_file_unchanged')
        self.assertTrue(any('does not prove' in item for item in packet['limitations']))


if __name__ == '__main__':
    unittest.main()

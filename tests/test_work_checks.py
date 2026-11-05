import unittest
from amadeus.work_checks import inspect_files


class WorkChecksTests(unittest.TestCase):
    def test_checks_python_and_json_without_executing_code(self):
        files = {'ok.py': {'text': "raise RuntimeError('not executed')\n"},
                 'bad.py': {'text': 'def broken(:\n    pass\n'},
                 'return.py': {'text': 'return 2\n'},
                 'good.json': {'text': '{"ok": true}'},
                 'bad.json': {'text': '{"ok": }'},
                 'nonfinite.json': {'text': '{"x": NaN}'},
                 'notes.md': {'text': '# Notes'}, 'missing.py': None}
        result = {x['path']: x for x in inspect_files(files)}
        self.assertEqual(result['ok.py']['status'], 'pass')
        self.assertEqual(result['bad.py']['status'], 'fail')
        self.assertEqual(result['bad.py']['line'], 1)
        self.assertEqual(result['return.py']['status'], 'fail')
        self.assertEqual(result['good.json']['status'], 'pass')
        self.assertEqual(result['bad.json']['status'], 'fail')
        self.assertEqual(result['nonfinite.json']['status'], 'fail')
        self.assertEqual(result['missing.py']['status'], 'missing')
        self.assertNotIn('notes.md', result)

if __name__ == '__main__':
    unittest.main()

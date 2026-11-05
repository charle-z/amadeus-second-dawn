"""Read-only, deterministic syntax checks; these never execute selected code."""
import json
from pathlib import PurePosixPath


def _reject_nonfinite(_value):
    raise ValueError("Non-finite JSON number")


def inspect_files(files):
    results = []
    for path, snapshot in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix not in ('.py', '.json'):
            continue
        check = 'python-syntax' if suffix == '.py' else 'json-syntax'
        item = {'path': path, 'check': check}
        if snapshot is None:
            item['status'] = 'missing'
        else:
            try:
                if suffix == '.py':
                    compile(snapshot['text'], '<selected file>', 'exec', dont_inherit=True)
                else:
                    json.loads(snapshot['text'], parse_constant=_reject_nonfinite)
                item['status'] = 'pass'
            except (SyntaxError, json.JSONDecodeError) as exc:
                item.update(status='fail', line=exc.lineno, column=exc.offset if isinstance(exc, SyntaxError) else exc.colno)
            except (ValueError, RecursionError):
                item.update(status='fail', line=None, column=None)
        results.append(item)
    return results

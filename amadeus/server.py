"""Local-only web interface. All model calls and the API key stay on the server."""
import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Experiment
from .muse import MuseAgent
from .cells import CellCoordinator, MAX_SLOTS, MAX_CALLS, MAX_OUTPUT, CALLS_PER_CELL

WEB = Path(__file__).resolve().parent.parent / 'web'
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
          '/world.js': ('world.js', 'application/javascript; charset=utf-8'),
          '/results.js': ('results.js', 'application/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, db_path, port):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.busy = threading.Lock()
        self.work_root = os.environ.get('AMADEUS_WORKSPACE')
        self.cells = CellCoordinator()
        exp = Experiment(self.db_path)
        try:
            exp.db.execute('CREATE TABLE IF NOT EXISTS ui_comparisons (id INTEGER PRIMARY KEY, result TEXT NOT NULL)')
            exp.db.execute('CREATE TABLE IF NOT EXISTS ui_cell_runs (id INTEGER PRIMARY KEY, result TEXT NOT NULL)')
            exp.db.commit()
        finally:
            exp.close()
        super().__init__(('127.0.0.1', port), Handler)


def make_server(db_path, port=8765):
    return Server(db_path, port)


def integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid integer')
    return value


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def valid_host(self):
        port = self.server.server_port
        return self.headers.get('Host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, body):
        self.send_bytes(status, json.dumps(body, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        if not self.valid_host():
            return self.send_json(403, {'error': 'Invalid host'})
        if self.path in STATIC:
            filename, content_type = STATIC[self.path]
            return self.send_bytes(200, (WEB / filename).read_bytes(), content_type)
        if self.path != '/api/state':
            return self.send_json(404, {'error': 'Not found'})
        exp = Experiment(self.server.db_path)
        try:
            rows = exp.db.execute('SELECT id FROM generations ORDER BY id DESC LIMIT 100').fetchall()
            generations = []
            for row in rows:
                generation = exp.get_generation(row['id'])
                generation['events'] = exp.events(row['id'])
                generations.append(generation)
            comparisons = [json.loads(row['result']) for row in
                           exp.db.execute('SELECT result FROM ui_comparisons ORDER BY id DESC LIMIT 10')]
            cell_runs = [json.loads(row['result']) for row in
                         exp.db.execute('SELECT result FROM ui_cell_runs ORDER BY id DESC LIMIT 10')]
            from .work import WorkManager
            work = WorkManager(exp.db, self.server.work_root)
            self.send_json(200, {'work_available': work.root is not None, 'work_tasks': work.list_tasks(),
                                 'generations': generations, 'memories': exp.memories(), 'comparisons': comparisons,
                                 'cell_runs': cell_runs, 'cell_reservations': self.server.cells.snapshot(),
                                 'cell_capacity': {'max_concurrent_cells': MAX_SLOTS, 'max_calls': MAX_CALLS,
                                                   'max_output_tokens': MAX_OUTPUT, 'per_cell_calls': CALLS_PER_CELL}})
        finally:
            exp.close()

    def do_POST(self):
        if not self.valid_host() or (self.headers.get('Origin') and
                self.headers['Origin'] != 'http://' + self.headers.get('Host', '')):
            return self.send_json(403, {'error': 'Invalid origin'})
        if self.headers.get_content_type() != 'application/json':
            return self.send_json(415, {'error': 'Expected application/json'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= 16384:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected JSON object')
            result = self.dispatch(data)
            self.send_json(200, result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.send_json(502, {'error': str(exc)})
        except Exception:
            self.send_json(500, {'error': 'Internal server error. Check the server log.'})
            import traceback
            traceback.print_exc()

    def dispatch(self, data):
        if self.path == '/api/planner':
            if set(data) != {'candidates', 'budgets'}:
                raise ValueError('Expected candidates and budgets')
            from .planner import select_exact
            return select_exact(data['candidates'], data['budgets'])
        exp = Experiment(self.server.db_path)
        try:
            if self.path == '/api/work/start' and set(data) == {'goal', 'paths'}:
                from .work import WorkManager
                return WorkManager(exp.db, self.server.work_root).start(data['goal'], data['paths'])
            if self.path == '/api/work/delete' and set(data) == {'task_id'}:
                task_id = integer(data['task_id'], 1, 2**53 - 1)
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    from .work import WorkManager
                    return WorkManager(exp.db, self.server.work_root).delete(task_id)
                finally:
                    self.server.busy.release()
            if self.path == '/api/work/resume' and set(data) == {'task_id'}:
                task_id = integer(data['task_id'], 1, 2**53 - 1)
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    from .work import WorkManager, MuseWorkAgent
                    return WorkManager(exp.db, self.server.work_root).resume(task_id, MuseWorkAgent())
                finally:
                    self.server.busy.release()
            if self.path == '/api/start' and set(data) == {'version', 'seed'}:
                if data['version'] not in ('v1', 'v2'):
                    raise ValueError('Invalid world version')
                return {'generation': exp.start(data['version'], integer(data['seed'], -1000000000, 1000000000))}
            if self.path in ('/api/step', '/api/restart') and set(data) == {'generation_id'}:
                generation_id = integer(data['generation_id'], 1, 2**53 - 1)
                if self.path == '/api/restart':
                    return {'generation': exp.restart(generation_id)}
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    return exp.step(generation_id, MuseAgent())
                finally:
                    self.server.busy.release()
            if self.path in ('/api/continue-changed', '/api/verified-step') and set(data) == {'generation_id'}:
                generation_id = integer(data['generation_id'], 1, 2**53 - 1)
                if self.path == '/api/continue-changed':
                    return {'generation': exp.continue_changed(generation_id)}
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    from .arena import MuseArenaAgent
                    return exp.verified_step(generation_id, MuseArenaAgent())
                finally:
                    self.server.busy.release()
            if self.path == '/api/comparison' and set(data) in ({'seeds'}, {'seeds', 'inspection_mode'}):
                mode = data.get('inspection_mode', 'optional')
                if mode not in ('optional', 'matched'):
                    raise ValueError('Invalid inspection mode')
                seeds = data['seeds']
                if not isinstance(seeds, list) or not 1 <= len(seeds) <= 2:
                    raise ValueError('Choose one or two seeds')
                seeds = [integer(s, -1000000000, 1000000000) for s in seeds]
                if len(set(seeds)) != len(seeds):
                    raise ValueError('Seeds must be unique')
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    from .arena import run_comparison, MuseArenaAgent, ComparisonInterrupted
                    try:
                        result = run_comparison(exp.memories(), seeds, MuseArenaAgent(), inspection_mode=mode)
                    except ComparisonInterrupted as exc:
                        result = exc.partial_result
                    with exp.db:
                        exp.db.execute('INSERT INTO ui_comparisons(result) VALUES (?)', (json.dumps(result),))
                    return result
                finally:
                    self.server.busy.release()
            if self.path == '/api/cells' and set(data) == {'seed'}:
                seed = integer(data['seed'], -1000000000, 1000000000)
                if not self.server.busy.acquire(blocking=False):
                    raise ValueError('Another model run is in progress')
                try:
                    from .arena import MuseArenaAgent
                    result = self.server.cells.run(exp.memories(), seed, lambda strategy: MuseArenaAgent())
                    if result['status'] not in ('complete', 'partial'):
                        raise RuntimeError('Invalid cell run status')
                    with exp.db:
                        exp.db.execute('INSERT INTO ui_cell_runs(result) VALUES (?)', (json.dumps(result),))
                    return result
                finally:
                    self.server.busy.release()
            raise ValueError('Unknown endpoint or invalid fields')
        finally:
            exp.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='.runtime/experiment.sqlite3')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.db, args.port)
    print(f'AMADEUS: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

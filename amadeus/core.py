"""Small deterministic world and durable, independently evaluated episodes."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_gate(version, seed):
    if version not in ("v1", "v2") or type(seed) is not int:
        raise ValueError("Invalid world version or seed")
    # The same seed supplies the same environment; v2 reverses its gate rule.
    bit = hashlib.sha256(str(seed).encode()).digest()[0] & 1
    if version == "v2":
        bit ^= 1
    return ("left", "right")[bit]


def observe(version, seed):
    safe_gate(version, seed)  # validate inputs
    return {"world_version": version, "seed": seed,
            "scene": "Two gates block the exit. One leads to safety; the other is fatal.",
            "actions": ["left", "right"], "goal": "Reach the exit alive."}


def validate_decision(value):
    if not isinstance(value, dict) or set(value) != {"action", "rationale"}:
        raise ValueError("Decision must have exactly action and rationale")
    if value["action"] not in ("left", "right"):
        raise ValueError("Invalid action")
    if not isinstance(value["rationale"], str) or not 1 <= len(value["rationale"].strip()) <= 500:
        raise ValueError("Invalid rationale")
    return value


class Experiment:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS generations (
          id INTEGER PRIMARY KEY, world_version TEXT NOT NULL, seed INTEGER NOT NULL,
          status TEXT NOT NULL, parent_id INTEGER REFERENCES generations(id), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id),
          kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memories (
          id INTEGER PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id),
          world_version TEXT NOT NULL, seed INTEGER NOT NULL, action TEXT NOT NULL,
          outcome TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def _event(self, generation_id, kind, data):
        self.db.execute("INSERT INTO events(generation_id,kind,data,created_at) VALUES (?,?,?,?)",
                        (generation_id, kind, json.dumps(data), now()))

    def _start(self, version, seed, parent_id=None):
        observation = observe(version, seed)
        row = self.db.execute("INSERT INTO generations(world_version,seed,status,parent_id,created_at) VALUES (?,?,?,?,?)",
                              (version, seed, "alive", parent_id, now()))
        self._event(row.lastrowid, "birth", observation)
        return self.get_generation(row.lastrowid)

    def start(self, version="v1", seed=1):
        with self.db:
            return self._start(version, seed)

    def get_generation(self, generation_id):
        row = self.db.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
        if row is None:
            raise ValueError("Generation not found")
        result = dict(row)
        result["observation"] = observe(result["world_version"], result["seed"])
        return result

    def memories(self):
        rows = self.db.execute("SELECT * FROM memories ORDER BY id").fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["evidence"] = json.loads(row["evidence"])
        return result

    def events(self, generation_id):
        rows = self.db.execute("SELECT * FROM events WHERE generation_id=? ORDER BY id", (generation_id,)).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["data"] = json.loads(row["data"])
        return result

    def step(self, generation_id, decide):
        generation = self.get_generation(generation_id)
        if generation["status"] != "alive":
            raise ValueError("Generation is not alive")
        decision = validate_decision(decide(generation["observation"], self.memories()))
        outcome = "won" if decision["action"] == safe_gate(generation["world_version"], generation["seed"]) else "dead"
        evidence = {"observation": generation["observation"], "action": decision["action"],
                    "result": outcome, "evaluator": "deterministic gate rule"}
        with self.db:
            changed = self.db.execute("UPDATE generations SET status=? WHERE id=? AND status='alive'", (outcome, generation_id))
            if changed.rowcount != 1:
                raise ValueError("Generation changed while model was deciding")
            self._event(generation_id, "decision", decision)
            self._event(generation_id, outcome, evidence)
            row = self.db.execute("INSERT INTO memories(generation_id,world_version,seed,action,outcome,evidence,created_at) VALUES (?,?,?,?,?,?,?)",
                (generation_id, generation["world_version"], generation["seed"], decision["action"], outcome, json.dumps(evidence), now()))
            memory = dict(self.db.execute("SELECT * FROM memories WHERE id=?", (row.lastrowid,)).fetchone())
            memory["evidence"] = json.loads(memory["evidence"])
        return {"generation_id": generation_id, "decision": decision, "status": outcome, "memory": memory}

    def restart(self, generation_id):
        generation = self.get_generation(generation_id)
        with self.db:
            if generation["status"] == "alive":
                changed = self.db.execute("UPDATE generations SET status='killed' WHERE id=? AND status='alive'", (generation_id,))
                if changed.rowcount != 1:
                    raise ValueError("Generation changed while restarting")
                self._event(generation_id, "killed", {"reason": "manual restart"})
            return self._start(generation["world_version"], generation["seed"], generation_id)

    def continue_changed(self, generation_id):
        """Create a linked v2 generation after a recorded v1 outcome."""
        with self.db:
            generation = self.get_generation(generation_id)
            if generation['world_version'] != 'v1' or generation['status'] not in ('won', 'dead'):
                raise ValueError('A completed v1 generation is required')
            if not self.db.execute('SELECT 1 FROM memories WHERE generation_id=?', (generation_id,)).fetchone():
                raise ValueError('A recorded memory is required')
            return self._start('v2', generation['seed'], generation_id)

    def verified_step(self, generation_id, decide):
        """Ask the model to assess the parent's evidence and act in v2."""
        from .arena import _trial, _TrackedDecision
        generation = self.get_generation(generation_id)
        if generation['status'] != 'alive' or generation['world_version'] != 'v2' or generation['parent_id'] is None:
            raise ValueError('An alive changed-world generation is required')
        parent = self.get_generation(generation['parent_id'])
        if parent['world_version'] != 'v1' or parent['seed'] != generation['seed'] or parent['status'] not in ('won', 'dead'):
            raise ValueError('A completed v1 parent with the same seed is required')
        memories = [m for m in self.memories() if m['generation_id'] == parent['id']]
        if not memories:
            raise ValueError('The parent has no recorded memory')
        tracked = _TrackedDecision(decide)
        try:
            trial = _trial(generation['seed'], 'shifted', 'VERIFIED_MEMORY', memories, tracked, inspection_mode='matched')
        except Exception as exc:
            error_type = type(exc).__name__ if type(exc).__name__ in ('RuntimeError', 'ValueError', 'TimeoutError', 'OSError') else 'ModelError'
            with self.db:
                self._event(generation_id, 'verified_interrupted', {'stage': tracked.stage,
                            'model_calls': tracked.calls, 'usage': tracked.last_usage, 'error_type': error_type})
            if isinstance(exc, ValueError):
                raise ValueError('Model decision was invalid; partial evidence was recorded') from None
            raise RuntimeError('Muse request failed; partial evidence was recorded') from None
        decision = validate_decision({'action': trial['action'], 'rationale': trial['rationale']})
        outcome = 'won' if decision['action'] == safe_gate(generation['world_version'], generation['seed']) else 'dead'
        evidence = {'observation': generation['observation'], 'action': decision['action'],
                    'result': outcome, 'evaluator': 'deterministic gate rule',
                    'source_memory_ids': [m['id'] for m in memories],
                    'assessment': trial['assessment'], 'inspection': trial['inspection']}
        with self.db:
            changed = self.db.execute("UPDATE generations SET status=? WHERE id=? AND status='alive'", (outcome, generation_id))
            if changed.rowcount != 1:
                self._event(generation_id, 'verified_interrupted', {'stage': 'commit',
                            'model_calls': tracked.calls, 'usage': None, 'error_type': 'GenerationChanged'})
            else:
                self._event(generation_id, 'verified_trial', trial)
                self._event(generation_id, 'decision', decision)
                self._event(generation_id, outcome, evidence)
                row = self.db.execute('INSERT INTO memories(generation_id,world_version,seed,action,outcome,evidence,created_at) VALUES (?,?,?,?,?,?,?)',
                                      (generation_id, generation['world_version'], generation['seed'], decision['action'], outcome, json.dumps(evidence), now()))
                memory = dict(self.db.execute('SELECT * FROM memories WHERE id=?', (row.lastrowid,)).fetchone())
                memory['evidence'] = json.loads(memory['evidence'])
        if changed.rowcount != 1:
            raise ValueError('Generation changed while model was deciding; partial evidence was recorded')
        return {'generation_id': generation_id, 'decision': decision, 'status': outcome, 'memory': memory, 'trial': trial}

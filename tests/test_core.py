import tempfile
import unittest
from pathlib import Path

from amadeus.core import Experiment, validate_decision, safe_gate


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "runs.sqlite3"
        self.exp = Experiment(self.db)

    def tearDown(self):
        self.exp.close()
        self.tmp.cleanup()

    def test_decision_validation_rejects_invalid_and_extra(self):
        self.assertEqual(validate_decision({"action": "left", "rationale": "test"})["action"], "left")
        for value in [{"action": "fly", "rationale": "x"}, {"action": "left"}, {"action": "left", "rationale": "", "win": True}, "left"]:
            with self.assertRaises(ValueError):
                validate_decision(value)

    def test_actual_decision_consequence_memory_and_restart(self):
        initial = self.exp.start("v1", 7)
        wrong = "right" if safe_gate("v1", 7) == "left" else "left"
        called = []
        def model(observation, memories):
            called.append((observation, memories))
            return {"action": wrong, "rationale": "chosen by test model"}
        result = self.exp.step(initial["id"], model)
        self.assertEqual(len(called), 1)
        self.assertEqual(result["status"], "dead")
        self.assertEqual(result["memory"]["outcome"], "dead")
        self.assertEqual(result["memory"]["world_version"], "v1")
        self.assertEqual(result["memory"]["generation_id"], initial["id"])
        self.assertEqual(result["memory"]["evidence"]["action"], wrong)
        again = self.exp.restart(initial["id"])
        self.assertNotEqual(initial["id"], again["id"])
        self.assertEqual(initial["observation"], again["observation"])
        self.exp.close()
        self.exp = Experiment(self.db)
        self.assertEqual(len(self.exp.memories()), 1)
        self.assertEqual(self.exp.get_generation(again["id"])["status"], "alive")

    def test_backend_alone_decides_win(self):
        initial = self.exp.start("v1", 1)
        action = safe_gate("v1", 1)
        result = self.exp.step(initial["id"], lambda *_: {"action": action, "rationale": "guess"})
        self.assertEqual(result["status"], "won")
        with self.assertRaises(ValueError):
            self.exp.step(initial["id"], lambda *_: {"action": action, "rationale": "again"})

    def test_kill_alive_and_restart_creates_event_and_preserves_memories(self):
        run = self.exp.start("v2", 42)
        new = self.exp.restart(run["id"])
        self.assertEqual(self.exp.get_generation(run["id"])["status"], "killed")
        self.assertEqual(new["observation"], run["observation"])
        self.assertEqual([x["kind"] for x in self.exp.events(run["id"])], ["birth", "killed"])

    def test_second_life_preserves_parent_and_verifies_before_deciding(self):
        first = self.exp.start('v1', 7)
        old = self.exp.step(first['id'], lambda *_: {'action': 'left', 'rationale': 'first'})
        child = self.exp.continue_changed(first['id'])
        self.assertEqual((child['world_version'], child['seed'], child['parent_id']), ('v2', 7, first['id']))
        calls = []
        def decide(stage, context):
            calls.append((stage, context))
            if stage == 'assess':
                return {'memory_id': old['memory']['id'], 'evidence_id': 'inspection-1',
                        'verdict': 'applicable', 'rationale': 'signal supports this'}
            return {'action': 'left', 'rationale': 'choice based on observation'}
        result = self.exp.verified_step(child['id'], decide)
        self.assertEqual([x[0] for x in calls], ['assess', 'act'])
        self.assertEqual(calls[0][1]['memories'][0]['id'], old['memory']['id'])
        self.assertEqual(result['status'], 'won' if safe_gate('v2', 7) == 'left' else 'dead')
        self.assertEqual(result['trial']['assessment']['verdict'], 'applicable')
        self.assertEqual(result['memory']['evidence']['source_memory_ids'], [old['memory']['id']])
        self.assertEqual(len(self.exp.memories()), 2)
        self.exp.close(); self.exp = Experiment(self.db)
        self.assertIn('verified_trial', [e['kind'] for e in self.exp.events(child['id'])])
        self.assertEqual(self.exp.get_generation(child['id'])['status'], result['status'])

    def test_second_life_failure_leaves_child_alive_and_memory_intact(self):
        first = self.exp.start('v1', 7)
        with self.assertRaises(ValueError):
            self.exp.continue_changed(first['id'])
        self.exp.step(first['id'], lambda *_: {'action': 'left', 'rationale': 'first'})
        child = self.exp.continue_changed(first['id'])
        def fail(stage, context):
            raise RuntimeError('provider unavailable')
        with self.assertRaises(RuntimeError):
            self.exp.verified_step(child['id'], fail)
        self.assertEqual(self.exp.get_generation(child['id'])['status'], 'alive')
        self.assertEqual(len(self.exp.memories()), 1)
        self.assertEqual([e['kind'] for e in self.exp.events(child['id'])], ['birth', 'verified_interrupted'])
        with self.assertRaises(ValueError):
            self.exp.verified_step(first['id'], fail)

    def test_second_life_failure_preserves_valid_prior_assessment(self):
        first = self.exp.start('v1', 7)
        old = self.exp.step(first['id'], lambda *_: {'action': 'left', 'rationale': 'first'})
        child = self.exp.continue_changed(first['id'])
        class FailingAgent:
            last_usage = None
            def __call__(self, stage, context):
                if stage == 'assess':
                    self.last_usage = {'completion_tokens': 11}
                    return {'memory_id': old['memory']['id'], 'evidence_id': 'inspection-1',
                            'verdict': 'uncertain', 'rationale': 'first call'}
                self.last_usage = {'completion_tokens': 25, 'secret': 'PRIVATE'}
                raise RuntimeError('PRIVATE')
        with self.assertRaisesRegex(RuntimeError, 'partial evidence') as error:
            self.exp.verified_step(child['id'], FailingAgent())
        self.assertNotIn('PRIVATE', str(error.exception))
        data = self.exp.events(child['id'])[-1]['data']
        self.assertEqual(data['stage'], 'act')
        self.assertEqual(data['model_calls'][0]['response']['verdict'], 'uncertain')
        self.assertEqual(data['usage'], {'completion_tokens': 25})
        self.assertNotIn('outcome', data)
        self.assertEqual(self.exp.get_generation(child['id'])['status'], 'alive')

    def test_second_life_killed_during_model_does_not_record_false_outcome(self):
        first = self.exp.start('v1', 7)
        old = self.exp.step(first['id'], lambda *_: {'action': 'left', 'rationale': 'first'})
        child = self.exp.continue_changed(first['id'])
        def decide(stage, context):
            if stage == 'assess':
                return {'memory_id': old['memory']['id'], 'evidence_id': 'inspection-1',
                        'verdict': 'applicable', 'rationale': 'test'}
            self.exp.restart(child['id'])
            return {'action': 'left', 'rationale': 'test'}
        with self.assertRaises(ValueError):
            self.exp.verified_step(child['id'], decide)
        self.assertEqual(self.exp.get_generation(child['id'])['status'], 'killed')
        self.assertEqual(len(self.exp.memories()), 1)
        self.assertFalse(any(e['kind'] == 'decision' for e in self.exp.events(child['id'])))
        interrupted = self.exp.events(child['id'])[-1]['data']
        self.assertEqual(interrupted['error_type'], 'GenerationChanged')
        self.assertEqual(len(interrupted['model_calls']), 2)
        self.assertNotIn('outcome', interrupted)

    def test_invalid_model_output_has_no_side_effect(self):
        run = self.exp.start("v1", 5)
        with self.assertRaises(ValueError):
            self.exp.step(run["id"], lambda *_: {"action": "win", "rationale": "yes"})
        self.assertEqual(self.exp.get_generation(run["id"])["status"], "alive")
        self.assertEqual(self.exp.memories(), [])


if __name__ == "__main__":
    unittest.main()

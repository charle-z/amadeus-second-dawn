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

    def test_invalid_model_output_has_no_side_effect(self):
        run = self.exp.start("v1", 5)
        with self.assertRaises(ValueError):
            self.exp.step(run["id"], lambda *_: {"action": "win", "rationale": "yes"})
        self.assertEqual(self.exp.get_generation(run["id"])["status"], "alive")
        self.assertEqual(self.exp.memories(), [])


if __name__ == "__main__":
    unittest.main()

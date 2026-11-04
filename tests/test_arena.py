import unittest
from amadeus.arena import run_comparison, actual_safe_gate, inspection_hint


class ArenaTests(unittest.TestCase):
    def setUp(self):
        self.memories = [{"id": 11, "generation_id": 9, "world_version": "v1", "seed": 7,
                          "action": "left", "outcome": "dead", "evidence": {"result": "dead"}}]
        self.calls = []

    def decide(self, stage, context):
        self.calls.append((stage, context))
        if stage == "assess":
            return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "uncertain", "rationale": "Noisy observation"}
        action = "inspect" if context["inspection"] is None else "left"
        return {"action": action, "rationale": "My choice"}

    def test_paired_comparison_and_frozen_memories(self):
        result = run_comparison(self.memories, [7], self.decide)
        trials = result["trials"]
        self.assertEqual(len(trials), 6)
        self.assertTrue(all(x["cost"] == 1 and x["inspection"] for x in trials))
        self.assertEqual({x["strategy"] for x in trials}, {"NO_MEMORY", "NAIVE_MEMORY", "VERIFIED_MEMORY"})
        for strategy in ("NO_MEMORY", "NAIVE_MEMORY", "VERIFIED_MEMORY"):
            a, b = [x for x in trials if x["strategy"] == strategy]
            self.assertEqual({a["scenario"], b["scenario"]}, {"stable", "shifted"})
            self.assertNotEqual(a["outcome"], b["outcome"])
        assessed = [context for stage, context in self.calls if stage == "assess"]
        self.assertEqual(len(assessed), 2)
        self.assertTrue(all(x["inspection"]["id"] == "inspection-1" for x in assessed))
        verified_actions = [context for stage, context in self.calls if stage == "act" and context["strategy"] == "VERIFIED_MEMORY"]
        self.assertTrue(all(not x["memories"] for x in verified_actions))
        no_memory = [context for stage, context in self.calls if stage == "act" and context["strategy"] == "NO_MEMORY"]
        self.assertTrue(all(not x["memories"] for x in no_memory))
        self.assertEqual(self.memories[0]["evidence"], {"result": "dead"})
        self.assertEqual(sum(x["trials"] for x in result["summary"]), 6)
        self.assertEqual(len(result["scenario_summary"]), 6)

    def test_applicable_passes_only_assessed_memory(self):
        memories = self.memories + [{**self.memories[0], "id": 12}]
        contexts = []
        def decide(stage, context):
            if stage == "assess":
                return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "applicable", "rationale": "matches"}
            if context["strategy"] == "VERIFIED_MEMORY":
                contexts.append(context)
            return {"action": "left", "rationale": "choice"}
        run_comparison(memories, [7], decide)
        self.assertTrue(all([m["id"] for m in c["memories"]] == [11] for c in contexts))

    def test_refuses_missing_training_and_invalid_model_assessment(self):
        with self.assertRaises(ValueError):
            run_comparison([], [7], self.decide)
        with self.assertRaises(ValueError):
            run_comparison(self.memories, [8], self.decide)
        for key, bad in (("memory_id", 999), ("evidence_id", "unknown")):
            def decide(stage, context):
                if stage == "assess":
                    value = {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "applicable", "rationale": "x"}
                    value[key] = bad
                    return value
                return {"action": "left", "rationale": "x"}
            with self.assertRaises(ValueError):
                run_comparison(self.memories, [7], decide)

    def test_non_verified_can_win_without_inspection(self):
        def choose(stage, context):
            if stage == "assess":
                return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "inapplicable", "rationale": "different"}
            return {"action": "left", "rationale": "choice"}
        trials = run_comparison(self.memories, [7], choose)["trials"]
        self.assertTrue(any(t["outcome"] == "won" and t["cost"] == 0 for t in trials if t["strategy"] != "VERIFIED_MEMORY"))
        self.assertTrue(all(t["cost"] == 1 for t in trials if t["strategy"] == "VERIFIED_MEMORY"))

    def test_inspection_is_not_an_infallible_oracle(self):
        hits = [inspection_hint(s, "shifted") == actual_safe_gate(s, "shifted") for s in range(100)]
        self.assertIn(True, hits)
        self.assertIn(False, hits)

    def test_run_limits(self):
        for seeds in ([], [7, 7], [1, 2, 3], [True]):
            with self.assertRaises(ValueError):
                run_comparison(self.memories, seeds, self.decide)


if __name__ == "__main__":
    unittest.main()

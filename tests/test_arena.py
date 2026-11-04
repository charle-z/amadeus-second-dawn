import json
import unittest
from unittest.mock import patch
from amadeus.arena import run_comparison, actual_safe_gate, inspection_hint, MuseArenaAgent, MAX_COMPLETION_TOKENS, ComparisonInterrupted
from amadeus.core import safe_gate


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
        self.assertTrue(all(set(x["assessment"]) == {"verdict", "evidence_id"} for x in verified_actions))
        self.assertTrue(all("rationale" in t["assessment"] and "memory_id" in t["assessment"]
                            for t in trials if t["strategy"] == "VERIFIED_MEMORY"))
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

    def test_inapplicable_assessment_does_not_leak_to_action(self):
        contexts = []
        def choose(stage, context):
            if stage == "assess":
                return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "inapplicable",
                        "rationale": "The old left gate killed the agent"}
            if context["strategy"] == "VERIFIED_MEMORY":
                contexts.append(context)
            return {"action": "left", "rationale": "choice"}
        result = run_comparison(self.memories, [7], choose)
        self.assertTrue(all(c["memories"] == [] and c["assessment"] == {
            "verdict": "inapplicable", "evidence_id": "inspection-1"} for c in contexts))
        self.assertTrue(any("old left gate" in t["assessment"]["rationale"] for t in result["trials"]
                            if t["strategy"] == "VERIFIED_MEMORY"))

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

    def test_matched_inspection_is_shared_and_forced_across_policies(self):
        calls = []
        def decide(stage, context):
            calls.append((stage, context))
            self.assertIsNotNone(context["inspection"])
            self.assertFalse(context["can_inspect"])
            if stage == "assess":
                return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "uncertain", "rationale": "insufficient"}
            return {"action": "left", "rationale": "choice"}
        result = run_comparison(self.memories, [7], decide, inspection_mode="matched")
        self.assertEqual(result["inspection_mode"], "matched")
        self.assertEqual(len(result["trials"]), 6)
        for scenario in ("stable", "shifted"):
            group = [t for t in result["trials"] if t["scenario"] == scenario]
            self.assertEqual(len(group), 3)
            self.assertTrue(all(t["cost"] == 1 and t["inspection_mode"] == "matched" for t in group))
            self.assertTrue(all(t["inspection"] == group[0]["inspection"] for t in group))
        counts = {row["strategy"]: row["model_calls"] for row in result["summary"]}
        self.assertEqual(counts, {"NO_MEMORY": 2, "NAIVE_MEMORY": 2, "VERIFIED_MEMORY": 4})
        self.assertEqual(sum(stage == "assess" for stage, _ in calls), 2)
        self.assertTrue(any("additional" in x.lower() for x in result["limitations"]))

    def test_world_versions_and_evaluator_match_core_in_both_modes(self):
        memories = self.memories + [{**self.memories[0], "id": 12, "seed": 8}]
        def decide(stage, context):
            if stage == "assess":
                return {"memory_id": context["memories"][0]["id"], "evidence_id": "inspection-1",
                        "verdict": "uncertain", "rationale": "test"}
            return {"action": "left", "rationale": "test"}
        for mode in ("optional", "matched"):
            result = run_comparison(memories, [7, 8], decide, inspection_mode=mode)
            for trial in result["trials"]:
                version = "v1" if trial["scenario"] == "stable" else "v2"
                self.assertEqual(trial["world_version"], version)
                self.assertEqual(trial["observation"]["world_version"], version)
                self.assertEqual(actual_safe_gate(trial["seed"], trial["scenario"]), safe_gate(version, trial["seed"]))
                self.assertEqual(trial["outcome"], "won" if trial["action"] == safe_gate(version, trial["seed"]) else "dead")
            for seed in (7, 8):
                for strategy in ("NO_MEMORY", "NAIVE_MEMORY", "VERIFIED_MEMORY"):
                    group = [t for t in result["trials"] if t["seed"] == seed and t["strategy"] == strategy]
                    self.assertEqual({t["outcome"] for t in group}, {"won", "dead"})

    def test_default_and_explicit_optional_are_compatible(self):
        def decide(stage, context):
            if stage == "assess":
                return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "uncertain", "rationale": "test"}
            return {"action": "left", "rationale": "test"}
        default = run_comparison(self.memories, [7], decide)
        explicit = run_comparison(self.memories, [7], decide, inspection_mode="optional")
        self.assertEqual(default, explicit)
        self.assertEqual(default["inspection_mode"], "optional")
        self.assertTrue(all(t["cost"] == (1 if t["strategy"] == "VERIFIED_MEMORY" else 0)
                            for t in default["trials"]))

    def test_invalid_inspection_mode_does_not_call_model(self):
        for mode in ("bad", True, None):
            with self.assertRaises(ValueError):
                run_comparison(self.memories, [7], self.decide, inspection_mode=mode)
        self.assertEqual(self.calls, [])

    def test_interruption_preserves_completed_trials_and_safe_failed_usage(self):
        class FailDuringAssessment:
            last_usage = None
            def __call__(self, stage, context):
                if stage == "assess":
                    self.last_usage = {"completion_tokens": 20}
                    return {"memory_id": 11, "evidence_id": "inspection-1", "verdict": "uncertain", "rationale": "test"}
                if context["strategy"] == "VERIFIED_MEMORY":
                    self.last_usage = {"completion_tokens": 1024, "prompt_tokens": 0,
                                       "private": "NEVER EXPOSE", "completion_tokens_details": {"reasoning_tokens": 980}}
                    raise RuntimeError("NEVER EXPOSE private provider error")
                self.last_usage = {"completion_tokens": 12}
                return {"action": "left", "rationale": "test"}
        with self.assertRaises(ComparisonInterrupted) as caught:
            run_comparison(self.memories, [7], FailDuringAssessment(), inspection_mode="matched")
        partial = caught.exception.partial_result
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["completed_trials"], 2)
        self.assertEqual(partial["planned_trials"], 6)
        self.assertEqual(len(partial["trials"]), 2)
        self.assertEqual(partial["failed_attempt"]["stage"], "act")
        self.assertEqual(partial["failed_attempt"]["model_calls"][0]["stage"], "assess")
        self.assertEqual(partial["failed_attempt"]["model_calls"][0]["usage"]["completion_tokens"], 20)
        self.assertEqual(partial["failed_attempt"]["model_calls"][0]["response"]["verdict"], "uncertain")
        self.assertEqual(partial["failed_attempt"]["strategy"], "VERIFIED_MEMORY")
        self.assertEqual(partial["failed_attempt"]["usage"]["completion_tokens"], 1024)
        self.assertEqual(partial["failed_attempt"]["usage"]["prompt_tokens"], 0)
        self.assertNotIn("outcome", partial["failed_attempt"])
        self.assertNotIn("NEVER EXPOSE", json.dumps(partial) + str(caught.exception))

    def test_unknown_usage_is_not_counted_as_zero(self):
        class Failure:
            last_usage = None
            def __call__(self, stage, context):
                raise RuntimeError("unavailable")
        with self.assertRaises(ComparisonInterrupted) as caught:
            run_comparison(self.memories, [7], Failure())
        self.assertIsNone(caught.exception.partial_result["failed_attempt"]["usage"])
        self.assertEqual(caught.exception.partial_result["trials"], [])

    def test_run_limits(self):
        for seeds in ([], [7, 7], [1, 2, 3], [True]):
            with self.assertRaises(ValueError):
                run_comparison(self.memories, seeds, self.decide)


class ProviderDiagnosticsTests(unittest.TestCase):
    class Response:
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps(self.body).encode()

    def call(self, body):
        agent = MuseArenaAgent("sensitive-test-key")
        with patch("amadeus.arena.urlopen", return_value=self.Response(body)) as request:
            with self.assertRaises(RuntimeError) as caught:
                agent("act", {"can_inspect": True})
        self.assertNotIn("sensitive-test-key", str(caught.exception))
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["max_completion_tokens"], MAX_COMPLETION_TOKENS)
        return str(caught.exception)

    def test_current_completion_limit(self):
        self.assertEqual(MAX_COMPLETION_TOKENS, 1024)

    def test_length_error_reports_safe_token_counts(self):
        message = self.call({"choices": [{"finish_reason": "length", "message": {"content": "private memory"}}],
                             "usage": {"completion_tokens": 512, "prompt_tokens": 250,
                                       "completion_tokens_details": {"reasoning_tokens": 500}}})
        self.assertIn("finish_reason=length", message)
        self.assertIn("completion_tokens=512", message)
        self.assertIn("reasoning_tokens=500", message)
        self.assertNotIn("private memory", message)

    def test_provider_usage_survives_incomplete_response_and_is_sanitized(self):
        body = {"choices": [{"finish_reason": "length", "message": {"content": "private"}}],
                "usage": {"completion_tokens": 0, "prompt_tokens": 32, "private": "NEVER EXPOSE",
                          "completion_tokens_details": {"reasoning_tokens": 0, "private": "NEVER EXPOSE"}}}
        agent = MuseArenaAgent("sensitive-test-key")
        with patch("amadeus.arena.urlopen", return_value=self.Response(body)):
            with self.assertRaises(RuntimeError):
                agent("act", {"can_inspect": True})
        self.assertEqual(agent.last_usage, {"completion_tokens": 0, "prompt_tokens": 32,
                                           "completion_tokens_details": {"reasoning_tokens": 0}})

    def test_provider_missing_usage_remains_unknown(self):
        body = {"choices": [{"finish_reason": "length"}]}
        agent = MuseArenaAgent("sensitive-test-key")
        with patch("amadeus.arena.urlopen", return_value=self.Response(body)):
            with self.assertRaises(RuntimeError):
                agent("act", {"can_inspect": True})
        self.assertIsNone(agent.last_usage)

    def test_invalid_content_and_untrusted_finish_reason_are_redacted(self):
        msg = self.call({"choices": [{"finish_reason": "stop", "message": {"content": "PRIVATE NON JSON"}}]})
        self.assertIn("invalid", msg.lower())
        self.assertNotIn("PRIVATE", msg)
        msg = self.call({"choices": [{"finish_reason": "PRIVATE SECRET", "message": {"content": ""}}]})
        self.assertIn("finish_reason=other", msg)
        self.assertNotIn("PRIVATE", msg)

    def test_malformed_envelope_is_distinguished_without_raw_values(self):
        message = self.call({"choices": [], "usage": {"completion_tokens": "PRIVATE"}})
        self.assertIn("malformed", message.lower())
        self.assertNotIn("PRIVATE", message)


if __name__ == "__main__":
    unittest.main()

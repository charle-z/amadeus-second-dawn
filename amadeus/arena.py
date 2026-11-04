"""Paired trials with frozen training memories and model-led applicability checks.

The hidden evaluator owns outcomes. A noisy inspection is available to every
policy. This is a small demonstration, not a statistical benchmark.
"""
import copy
import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import safe_gate

STRATEGIES = ("NO_MEMORY", "NAIVE_MEMORY", "VERIFIED_MEMORY")
SCENARIOS = ("stable", "shifted")
MAX_COMPLETION_TOKENS = 1024


class ComparisonInterrupted(RuntimeError):
    """An in-progress comparison failed; completed evidence is in partial_result."""
    def __init__(self, partial_result):
        super().__init__("Comparison interrupted; partial evidence is available")
        self.partial_result = partial_result


class InvalidComparisonDecision(ComparisonInterrupted, ValueError):
    """A model decision was invalid; also preserves the ValueError contract."""


def _sanitize_usage(value):
    """Keep provider token counts only; unknown is None and known zero stays zero."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        item = value.get(key)
        if type(item) is int and 0 <= item <= 10000000:
            result[key] = item
    for key, count_keys in (("completion_tokens_details", ("reasoning_tokens",)),
                            ("prompt_tokens_details", ("cached_tokens",))):
        details = value.get(key)
        if isinstance(details, dict):
            clean = {k: details[k] for k in count_keys
                     if type(details.get(k)) is int and 0 <= details[k] <= 10000000}
            if clean:
                result[key] = clean
    return result or None


class _TrackedDecision:
    """Keep validated calls from the currently executing trial only."""
    def __init__(self, decide):
        self.decide = decide
        self.stage = None
        self.last_usage = None
        self.calls = []

    def __call__(self, stage, context):
        self.stage = stage
        self.last_usage = None
        try:
            value = self.decide(stage, context)
        finally:
            self.last_usage = _sanitize_usage(getattr(self.decide, "last_usage", None))
        valid = _validate_result(stage, value, context["memories"], context["can_inspect"])
        self.calls.append({"stage": stage, "response": valid, "usage": copy.deepcopy(self.last_usage)})
        return valid


def actual_safe_gate(seed, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("Invalid scenario")
    return safe_gate("v1" if scenario == "stable" else "v2", seed)


def inspection_hint(seed, scenario):
    gate = actual_safe_gate(seed, scenario)
    # The signal is wrong for one quarter of hash residues, not an oracle.
    residue = hashlib.sha256(f"probe:{seed}:{scenario}".encode()).digest()[0] % 4
    return ({"left": "right", "right": "left"}[gate] if residue == 0 else gate)


def _validate_result(stage, value, memories, can_inspect):
    if not isinstance(value, dict):
        raise ValueError("Model response must be an object")
    if stage == "assess":
        if set(value) != {"memory_id", "evidence_id", "verdict", "rationale"}:
            raise ValueError("Invalid applicability assessment fields")
        if type(value["memory_id"]) is not int or value["memory_id"] not in {m["id"] for m in memories}:
            raise ValueError("Assessment must reference a supplied memory")
        if value["evidence_id"] != "inspection-1":
            raise ValueError("Assessment must cite the current inspection")
        if value["verdict"] not in ("applicable", "inapplicable", "uncertain"):
            raise ValueError("Invalid applicability verdict")
    else:
        if set(value) != {"action", "rationale"}:
            raise ValueError("Invalid action fields")
        legal = ("left", "right", "inspect") if can_inspect else ("left", "right")
        if value["action"] not in legal:
            raise ValueError("Invalid or repeated action")
    if not isinstance(value["rationale"], str) or not 1 <= len(value["rationale"].strip()) <= 500:
        raise ValueError("Invalid rationale")
    return copy.deepcopy(value)


def _trial(seed, scenario, strategy, frozen, decide, inspection_mode="optional"):
    memories = [] if strategy == "NO_MEMORY" else copy.deepcopy(frozen)
    version = "v1" if scenario == "stable" else "v2"
    observation = {"world_version": version, "seed": seed,
                   "scene": "Two gates block the exit. One is fatal. The world may have changed since previous generations.",
                   "glyph": {"stable": "amber", "shifted": "violet"}[scenario],
                   "goal": "Reach the exit alive", "actions": ["left", "right", "inspect"],
                   "inspection_note": "An inspection costs one unit and gives an imperfect hint. It can be wrong."}
    training_ids = [m["id"] for m in memories]
    inspection, assessment, calls = None, None, []

    def call(stage, can_inspect):
        visible_assessment = assessment
        if (stage == "act" and assessment is not None
                and assessment["verdict"] != "applicable"):
            # The free-text rationale may quote a rejected memory. Keep the full
            # assessment in the audit trail, not in the subsequent prompt.
            visible_assessment = {"verdict": assessment["verdict"],
                                  "evidence_id": assessment["evidence_id"]}
        context = {"strategy": strategy, "observation": observation, "memories": memories,
                   "inspection": inspection, "assessment": visible_assessment,
                   "can_inspect": can_inspect}
        result = _validate_result(stage, decide(stage, copy.deepcopy(context)), memories, can_inspect)
        calls.append({"stage": stage, "response": result,
                      "usage": copy.deepcopy(getattr(decide, "last_usage", None))})
        return result

    def inspect():
        return {"id": "inspection-1", "hint": inspection_hint(seed, scenario), "cost": 1,
                "reliability": "imperfect; can be wrong"}

    if strategy == "VERIFIED_MEMORY":
        # Mandatory new observation: the model decides how it affects trust.
        inspection = inspect()
        assessment = call("assess", False)
        memories = ([m for m in memories if m["id"] == assessment["memory_id"]]
                    if assessment["verdict"] == "applicable" else [])
        choice = call("act", False)
    elif inspection_mode == "matched":
        inspection = inspect()
        choice = call("act", False)
    else:
        choice = call("act", True)
        if choice["action"] == "inspect":
            inspection = inspect()
            choice = call("act", False)
    action = choice["action"]
    outcome = "won" if action == actual_safe_gate(seed, scenario) else "dead"
    return {"strategy": strategy, "scenario": scenario, "world_version": version, "seed": seed,
            "inspection_mode": inspection_mode,
            "observation": observation, "training_memory_ids": training_ids,
            "inspection": inspection, "assessment": assessment, "action": action,
            "rationale": choice["rationale"], "outcome": outcome,
            "cost": 1 if inspection else 0, "model_calls": calls,
            "evidence": {"action": action, "outcome": outcome, "evaluator": "deterministic gate rule"}}


def run_comparison(frozen_memories, seeds, decide, inspection_mode="optional"):
    """Run matched policies on identical seeds and the same frozen v1 training set.

    Up to two unique seeds, each with at least one recorded v1 memory. Results
    only return after every real or explicitly injected decision has succeeded.
    """
    if inspection_mode not in ("optional", "matched"):
        raise ValueError("Inspection mode must be optional or matched")
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 2 or any(type(s) is not int or not -(2**63) <= s < 2**63 for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("Choose one or two distinct integer seeds")
    if not isinstance(frozen_memories, list):
        raise ValueError("Expected a list of training memories")
    frozen = copy.deepcopy(frozen_memories)
    by_seed = {}
    for seed in seeds:
        memories = [m for m in frozen if isinstance(m, dict) and m.get("world_version") == "v1"
                    and m.get("seed") == seed and type(m.get("id")) is int
                    and m.get("outcome") in ("won", "dead") and m.get("action") in ("left", "right")
                    and isinstance(m.get("evidence"), dict)]
        if not memories:
            raise ValueError(f"Seed {seed} needs at least one recorded v1 memory before comparison")
        # Limit prompt size; retain the latest four in stable id order.
        by_seed[seed] = sorted(memories, key=lambda m: m["id"])[-4:]
    trials = []
    for seed in seeds:
        for scenario in SCENARIOS:
            for strategy in STRATEGIES:
                tracked = _TrackedDecision(decide)
                try:
                    trials.append(_trial(seed, scenario, strategy, by_seed[seed], tracked, inspection_mode))
                except Exception as exc:
                    kind = type(exc).__name__
                    if kind not in ("RuntimeError", "ValueError", "TimeoutError", "OSError"):
                        kind = "ModelError"
                    partial = {"status": "partial", "inspection_mode": inspection_mode,
                               "planned_trials": len(seeds) * len(SCENARIOS) * len(STRATEGIES),
                               "completed_trials": len(trials), "trials": trials,
                               "failed_attempt": {"seed": seed, "scenario": scenario,
                                   "strategy": strategy, "stage": tracked.stage,
                                   "model_calls": tracked.calls, "usage": tracked.last_usage,
                                   "error_type": kind}}
                    error_class = InvalidComparisonDecision if isinstance(exc, ValueError) else ComparisonInterrupted
                    raise error_class(partial) from None
    summary = []
    for strategy in STRATEGIES:
        subset = [x for x in trials if x["strategy"] == strategy]
        summary.append({"strategy": strategy, "trials": len(subset),
                        "wins": sum(x["outcome"] == "won" for x in subset),
                        "deaths": sum(x["outcome"] == "dead" for x in subset),
                        "inspection_cost": sum(x["cost"] for x in subset),
                        "model_calls": sum(len(x["model_calls"]) for x in subset)})
    scenario_summary = []
    for strategy in STRATEGIES:
        for scenario in SCENARIOS:
            subset = [x for x in trials if x["strategy"] == strategy and x["scenario"] == scenario]
            scenario_summary.append({"strategy": strategy, "scenario": scenario, "trials": len(subset),
                                     "wins": sum(x["outcome"] == "won" for x in subset),
                                     "deaths": sum(x["outcome"] == "dead" for x in subset),
                                     "inspection_cost": sum(x["cost"] for x in subset)})
    return {"inspection_mode": inspection_mode, "trials": trials, "summary": summary, "scenario_summary": scenario_summary,
            "limitations": ["Inspection is noisy and costs one unit; it is not guaranteed correct.",
                            "Seeds pair the deterministic worlds, but model decisions are stochastic.",
                            "VERIFIED_MEMORY makes an additional model call to assess applicability.",
                            "World version is visible to the model; stable uses v1 and shifted uses v2.",
                            "Small samples do not establish a scientific performance advantage.",
                            "Memories are frozen before all trials; trials do not train each other."]}


class MuseArenaAgent:
    """Calls Meta's structured-output API; this class never substitutes a fake model."""
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set MODEL_API_KEY in the backend environment")
        self.last_usage = None

    def __call__(self, stage, context):
        if stage == "assess":
            properties = {"memory_id": {"type": "integer"},
                          "evidence_id": {"type": "string", "enum": ["inspection-1"]},
                          "verdict": {"type": "string", "enum": ["applicable", "inapplicable", "uncertain"]},
                          "rationale": {"type": "string"}}
            instruction = ("Assess whether one supplied memory applies to the current observation. "
                           "Cite evidence_id inspection-1. The inspection is imperfect evidence, not certain truth. If evidence is insufficient, say uncertain.")
        elif stage == "act":
            actions = ["left", "right"] + (["inspect"] if context["can_inspect"] else [])
            properties = {"action": {"type": "string", "enum": actions}, "rationale": {"type": "string"}}
            instruction = ("Choose an available action to reach the exit alive. Inspect is optional, has a cost, "
                           "and its hint can be wrong. Do not declare the result; the world evaluates it.")
        else:
            raise ValueError("Invalid model stage")
        payload = {"model": "muse-spark-1.3", "max_completion_tokens": MAX_COMPLETION_TOKENS, "reasoning_effort": "minimal",
                   "messages": [{"role": "user", "content": instruction + "\n" + json.dumps(context, ensure_ascii=False)}],
                   "response_format": {"type": "json_schema", "json_schema": {"name": stage, "strict": True,
                       "schema": {"type": "object", "properties": properties,
                                  "required": list(properties), "additionalProperties": False}}}}
        req = Request("https://api.meta.ai/v1/chat/completions", data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        self.last_usage = None
        try:
            with urlopen(req, timeout=60) as response:
                body = json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"Meta Model API returned HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(f"Meta Model API connection failed: {type(exc.reason).__name__}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError(f"Meta returned a malformed response envelope (stage={stage})") from None
        if not isinstance(body, dict):
            raise RuntimeError(f"Meta returned a malformed response envelope (stage={stage})")
        self.last_usage = _sanitize_usage(body.get("usage"))
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        details = usage.get("completion_tokens_details")
        details = details if isinstance(details, dict) else {}
        def diagnostic(reason):
            known = ("stop", "length", "content_filter", "tool_calls")
            safe_reason = reason if reason in known else ("missing" if reason is None else "other")
            parts = [f"stage={stage}", f"finish_reason={safe_reason}"]
            for label, value in (("prompt_tokens", usage.get("prompt_tokens")),
                                 ("completion_tokens", usage.get("completion_tokens")),
                                 ("reasoning_tokens", details.get("reasoning_tokens"))):
                if type(value) is int and 0 <= value <= 10000000:
                    parts.append(f"{label}={value}")
            return ", ".join(parts)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise RuntimeError(f"Meta returned a malformed response envelope ({diagnostic(None)})")
        choice = choices[0]
        reason = choice.get("finish_reason")
        if reason != "stop":
            raise RuntimeError(f"Meta returned an incomplete decision ({diagnostic(reason)})")
        try:
            result = json.loads(choice["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise RuntimeError(f"Meta returned invalid decision JSON ({diagnostic(reason)})") from None
        return result

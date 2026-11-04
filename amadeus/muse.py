"""Real Meta Model API adapter; no simulated fallback."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import validate_decision


class MuseAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set MODEL_API_KEY in the backend environment")
        self.last_usage = None

    def __call__(self, observation, memories):
        prompt = ("Choose exactly one action in this world. Treat past observations as evidence, "
                  "not as a guarantee. Explain briefly; do not claim to decide the outcome.\n" +
                  json.dumps({"observation": observation, "memories": memories}, ensure_ascii=False))
        payload = {"model": "muse-spark-1.3", "max_completion_tokens": 512,
                   "reasoning_effort": "minimal",
                   "messages": [{"role": "user", "content": prompt}],
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": "decision", "strict": True, "schema": {
                           "type": "object", "properties": {
                               "action": {"type": "string", "enum": ["left", "right"]},
                               "rationale": {"type": "string"}},
                           "required": ["action", "rationale"], "additionalProperties": False}}}}
        req = Request("https://api.meta.ai/v1/chat/completions",
                      data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=60) as response:
                body = json.loads(response.read())
        except HTTPError as exc:
            raise RuntimeError(f"Meta Model API returned HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(f"Meta Model API connection failed: {type(exc.reason).__name__}") from None
        try:
            choice = body["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Model response incomplete")
            result = validate_decision(json.loads(choice["message"]["content"]))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("Meta returned an invalid or incomplete decision") from exc
        self.last_usage = body.get("usage")
        return result

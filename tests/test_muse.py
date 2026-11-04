import json
import unittest
from unittest.mock import patch
from amadeus.muse import MuseAgent


class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps({"choices": [{"message": {"content": '{"action":"left","rationale":"try"}'}, "finish_reason": "stop"}], "usage": {"total_tokens": 12}}).encode()


class MuseTests(unittest.TestCase):
    def test_request_and_response(self):
        agent = MuseAgent("test-only")
        with patch("amadeus.muse.urlopen", return_value=Response()) as send:
            self.assertEqual(agent({"scene": "test"}, [])["action"], "left")
        request = send.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["response_format"]["json_schema"]["strict"], True)
        self.assertNotIn("test-only", request.data.decode())
        self.assertEqual(agent.last_usage["total_tokens"], 12)

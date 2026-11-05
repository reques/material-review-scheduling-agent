"""HTTP client contract tests; all responses below are simulated, not real runs."""
import json
import unittest
from unittest.mock import patch

from src.llm import LLMError, OpenAICompatibleClient
from src.guards import assemble_result


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.body).encode("utf-8")


class TestRealClientContract(unittest.TestCase):
    def test_realistic_draft_status_is_normalized_with_observed_save(self):
        result = assemble_result({"status": "draft", "suggested_slot": "19:00",
                                  "pending_confirmation": True},
                                 [{"slot": "19:00", "occupied": False},
                                  {"draft_saved": True, "draft_id": "D-1", "suggested_slot": "19:00",
                                   "pending_confirmation": True}], "18:00", "M01")
        self.assertEqual(result["status"], "draft_saved")
        self.assertTrue(result["draft_saved"])
        self.assertTrue(result["pending_confirmation"])

    def test_chat_completion_request_and_response(self):
        client = OpenAICompatibleClient(base_url="https://example.invalid/v1", api_key="test-key", model="test-model")
        response = FakeResponse({"model": "served-model", "choices": [{"message": {"content":
            '{"thought":"check","action":"get_material","action_input":{"material_id":"M01"}}'}}]})
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            decision = client.decide("test prompt")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://example.invalid/v1/chat/completions")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["messages"][1]["content"], "test prompt")
        self.assertEqual(decision["action"], "get_material")
        self.assertEqual(client.call_attempts, 1)
        self.assertEqual(client.response_models, ["served-model"])

    def test_invalid_model_output_is_not_counted_as_valid(self):
        client = OpenAICompatibleClient(base_url="https://example.invalid/v1", api_key="test-key", model="test-model")
        response = FakeResponse({"model": "served-model", "choices": [{"message": {"content": "not JSON"}}]})
        with patch("urllib.request.urlopen", return_value=response), self.assertRaises(LLMError):
            client.decide("test prompt")
        self.assertEqual(client.call_attempts, 1)
        self.assertEqual(client.response_models, [])

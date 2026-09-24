import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app


class AgentAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    @patch("app.main.run_job_agent")
    def test_returns_final_answer(self, run_agent):
        run_agent.return_value = {"messages": [AIMessage(content="Matching jobs")]}
        response = self.client.post("/api/agent", json={"prompt": " backend jobs "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"answer": "Matching jobs"})
        run_agent.assert_called_once_with("backend jobs")

    @patch("app.main.run_job_agent")
    def test_combines_text_blocks(self, run_agent):
        run_agent.return_value = {"messages": [AIMessage(content=[
            {"type": "text", "text": "Job A"},
            {"type": "text", "text": "Job B"},
        ])]}
        response = self.client.post("/api/agent", json={"prompt": "jobs"})
        self.assertEqual(response.json(), {"answer": "Job A\nJob B"})

    @patch("app.main.run_job_agent")
    def test_rejects_invalid_prompts_without_calling_agent(self, run_agent):
        for body in ({}, {"prompt": "  "}, {"prompt": 123}, {"prompt": "x" * 10001}):
            with self.subTest(body_type=type(body.get("prompt"))):
                response = self.client.post("/api/agent", json=body)
                self.assertEqual(response.status_code, 422)
        run_agent.assert_not_called()

    @patch("app.main.run_job_agent")
    def test_upstream_failure_does_not_expose_details(self, run_agent):
        run_agent.side_effect = RuntimeError("secret upstream detail")
        response = self.client.post("/api/agent", json={"prompt": "jobs"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret", response.text)

    @patch("app.main.run_job_agent")
    def test_empty_answer_returns_error(self, run_agent):
        run_agent.return_value = {"messages": [AIMessage(content="")]}
        response = self.client.post("/api/agent", json={"prompt": "jobs"})
        self.assertEqual(response.status_code, 502)

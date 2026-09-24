import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import JobStorageError, init_database, job_key, save_jobs
from app.main import app
from tools.himalayas import get_himalayas_job


class JobStorageTests(unittest.TestCase):
    @patch("tools.himalayas.save_jobs")
    @patch("tools.himalayas.requests.get")
    def test_saves_entire_page_before_returning_top_ten(self, get, save):
        jobs = [{"id": str(i), "title": f"Job {i}"} for i in range(15)]
        get.return_value.json.return_value = {"jobs": jobs}
        self.assertEqual(len(get_himalayas_job("backend")), 10)
        save.assert_called_once_with(jobs)

    @patch("tools.himalayas.save_jobs", side_effect=JobStorageError("failed"))
    @patch("tools.himalayas.requests.get")
    def test_storage_failure_propagates(self, get, save):
        get.return_value.json.return_value = {"jobs": [{"id": "1"}]}
        with self.assertRaises(JobStorageError):
            get_himalayas_job("backend")

    @patch("app.main.run_job_agent", side_effect=JobStorageError("secret"))
    def test_api_reports_storage_failure(self, run):
        client = TestClient(app)
        self.addCleanup(client.close)
        response = client.post("/api/agent", json={"prompt": "jobs"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)

    def test_identity_survives_updated_content(self):
        self.assertEqual(job_key({"id": "1", "title": "Old"}),
                         job_key({"id": "1", "title": "New"}))
        self.assertNotEqual(job_key({"title": "A"}), job_key({"title": "B"}))

    @patch("app.database.connect")
    def test_empty_results_need_no_write(self, connect):
        save_jobs([])
        connect.assert_not_called()


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not set")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_upsert_preserves_full_payload(self):
        import uuid
        import psycopg

        url = os.environ["TEST_DATABASE_URL"]
        identifier = str(uuid.uuid4())
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            init_database()
            job = {"id": identifier, "title": "Original", "extra": ["remote"]}
            try:
                save_jobs([job, job])
                job["title"] = "Updated"
                save_jobs([job])
                with psycopg.connect(url) as conn:
                    rows = conn.execute(
                        "SELECT title, raw_data FROM jobs WHERE source_key = %s",
                        ("id:" + identifier,),
                    ).fetchall()
                self.assertEqual(rows, [("Updated", job)])
            finally:
                with psycopg.connect(url) as conn:
                    conn.execute("DELETE FROM jobs WHERE source_key = %s",
                                 ("id:" + identifier,))

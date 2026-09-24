"""PostgreSQL storage for every job returned by the search provider."""

import hashlib
import json
import os

import psycopg
from psycopg.types.json import Jsonb

from app.config import init_config


class JobStorageError(RuntimeError):
    """Job persistence failed; do not return a successful search."""


def connect():
    init_config()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise JobStorageError("DATABASE_URL is required")
    return psycopg.connect(url, connect_timeout=5)


def init_database():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                title TEXT,
                company TEXT,
                apply_url TEXT,
                raw_data JSONB NOT NULL,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (source, source_key)
            )
        """)


def job_key(job: dict) -> str:
    for field in ("id", "guid", "slug", "applicationLink"):
        value = job.get(field)
        if value is not None and str(value).strip():
            return f"{field}:{value}"
    # Missing provider identifiers: use the entire payload to avoid merging
    # distinct positions with the same title and company.
    payload = json.dumps(job, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def save_jobs(jobs: list[dict]):
    if not jobs:
        return
    try:
        with connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO jobs
                        (source, source_key, title, company, apply_url, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source, source_key) DO UPDATE SET
                        title = EXCLUDED.title,
                        company = EXCLUDED.company,
                        apply_url = EXCLUDED.apply_url,
                        raw_data = EXCLUDED.raw_data,
                        last_seen_at = CURRENT_TIMESTAMP
                """, [
                    ("himalayas", job_key(job), job.get("title"),
                     job.get("companyName"), job.get("applicationLink"), Jsonb(job))
                    for job in jobs
                ])
    except Exception as exc:
        raise JobStorageError("Unable to save jobs") from exc

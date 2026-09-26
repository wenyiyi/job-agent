"""PostgreSQL storage for every job returned by the search provider."""

import hashlib
import json
import os

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

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


def list_jobs(query: str = "", page: int = 1, page_size: int = 20) -> dict:
    # Escape LIKE metacharacters so user input is treated as a literal search.
    pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    where = "WHERE COALESCE(title, '') ILIKE %s OR COALESCE(company, '') ILIKE %s"
    try:
        with connect() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                cursor.execute("SELECT COUNT(*) AS total FROM jobs " + where,
                               (pattern, pattern))
                total = cursor.fetchone()["total"]
                cursor.execute(
                    "SELECT id, title, company, apply_url, source, raw_data, last_seen_at "
                    "FROM jobs " + where +
                    " ORDER BY last_seen_at DESC, id DESC LIMIT %s OFFSET %s",
                    (pattern, pattern, page_size, (page - 1) * page_size),
                )
                return {"items": cursor.fetchall(), "total": total,
                        "page": page, "page_size": page_size}
    except Exception as exc:
        raise JobStorageError("Unable to read jobs") from exc


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

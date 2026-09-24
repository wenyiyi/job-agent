# job-agent

A LangChain-based agent for finding remote jobs, exposed through a FastAPI HTTP API.

## Run Locally

Activate your virtual environment, then run the following commands from the project root:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Configure model credentials (such as `GOOGLE_API_KEY`) in your local `.env` file. The `.env` file is ignored by Git; do not commit it.

### PostgreSQL

Start a local database before starting the API (requires Docker):

```bash
docker compose up -d postgres
```

Add the following to your existing `.env` file; see `.env.example` for a template:

```dotenv
DATABASE_URL=postgresql://job_agent:job_agent_local@localhost:5432/job_agent
```

These credentials are for local development only. For an existing PostgreSQL
server, set `DATABASE_URL` to its connection URL instead. The API creates the
`jobs` table at startup; the database user needs permission to create tables.
Startup fails if the database is unavailable or the URL is missing.

Every job in each Himalayas search response is saved before the first ten are
returned to the model. This does not fetch additional pages automatically.
The table stores title, company, application URL, the complete provider payload
in `raw_data` (JSONB), and first/last seen timestamps. Jobs are deduplicated by
provider ID, GUID, slug, or application URL, in that order. If none is available,
a hash of the complete payload is used; changes to such a payload create a new row.
Repeated searches update existing records. A failed batch is rolled back and
the API returns HTTP 503 if job storage fails. Saved jobs remain available even
if a later model call fails. Docker stores the database in a persistent volume.

Inspect saved jobs:

```bash
docker compose exec postgres psql -U job_agent -d job_agent -c 'SELECT id, title, company, apply_url FROM jobs ORDER BY last_seen_at DESC LIMIT 20;'
```

API documentation: http://127.0.0.1:8000/docs

## Query the Agent

```bash
curl -X POST http://127.0.0.1:8000/api/agent \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Find senior backend engineer jobs that hire worldwide."}'
```

Successful response:

```json
{"answer":"Job recommendations returned by the agent"}
```

The API waits for the agent to finish and returns its final text response, excluding internal tool-call messages.
After trimming leading and trailing whitespace, `prompt` must contain 1–10,000 characters. Invalid input returns HTTP 422.
If the agent call fails or returns no text, the API returns HTTP 502. Authentication is not currently configured, and the API runs locally by default.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

API tests mock the agent's responses and do not call real models or job APIs.
To also run the PostgreSQL integration test, set `TEST_DATABASE_URL` to a test
database connection URL before running the test suite. This test creates the
table if needed and removes its own test records afterward.

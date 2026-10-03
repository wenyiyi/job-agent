# job-agent

A LangGraph agent for finding remote jobs, exposed through FastAPI with a React frontend.

## Run Locally

### Start everything with Docker Compose

Create `.env` from `.env.example` if needed and configure `GOOGLE_API_KEY`.
Then start all services (or run the entire `compose.yaml` in PyCharm):

```bash
docker compose up -d --build
```

Open http://127.0.0.1:8000/ for the React page and
http://127.0.0.1:8000/docs for API documentation.
The image builds React automatically and runs FastAPI after PostgreSQL is healthy.
The web container uses `postgres:5432`; local tools use `localhost:5433`.
Select all services when launching Compose in PyCharm; selecting only `postgres`
starts only the database. Run the build command again after changing code.

```bash
docker compose logs -f web
docker compose down
```

Stopping with `down` preserves the database volume.

### Run without a web container

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
DATABASE_URL=postgresql://job_agent:job_agent_local@localhost:5433/job_agent
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

## Browse Saved Jobs

Open http://127.0.0.1:8000/ after starting PostgreSQL and FastAPI.
The responsive jobs page supports title/company search, pagination, job details,
and links to the original application pages. Use **Refresh** to load newly saved
jobs. Browsing only reads saved records; it does not trigger an agent search.
The React frontend uses Vite (Node.js 20.19+ or 22.12+). Build it before opening
the FastAPI homepage:

```bash
cd frontend
npm ci
npm run build
```

FastAPI serves `frontend/dist` at `/` and its generated assets at `/assets`.
For development, run `npm run dev` in `frontend` and open the URL printed by
Vite. Its `/api` proxy forwards requests to FastAPI at `127.0.0.1:8000`.
The page also accepts natural-language Agent queries and refreshes the saved
jobs after each query completes.
The interface defaults to English and supports Chinese using the language
selector in the header. The selection is saved in the browser. Job descriptions
and agent responses retain their original language.

The backend explicitly compiles a LangGraph `MessagesState` graph:
`START → agent → tools → agent`, ending when the model has no tool calls.
The system prompt is supplied on each model invocation. Tool errors propagate
to the API, and execution is capped at 25 graph steps.

The underlying read endpoint is `GET /api/jobs?q=backend&page=1&page_size=20`.
It returns `items`, `total`, `page`, and `page_size`, ordered by latest update.
Page sizes range from 1 to 100. Database read failures return HTTP 503.

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

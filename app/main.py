import logging
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from agent.workflow import run_job_agent
from app.database import JobStorageError, init_database, list_jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(init_database)
    yield

logger = logging.getLogger(__name__)
app = FastAPI(title="Job Agent API", lifespan=lifespan)
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(static_dir / "index.html")


@app.get("/api/jobs")
def saved_jobs(q: str = Query("", max_length=200),
               page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100)):
    try:
        return list_jobs(q.strip(), page, page_size)
    except JobStorageError as exc:
        logger.error("Unable to read saved jobs")
        raise HTTPException(status_code=503, detail="暂时无法读取岗位，请稍后重试。") from exc


class AgentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(min_length=1, max_length=10000)


class AgentResponse(BaseModel):
    answer: str


@app.post("/api/agent", response_model=AgentResponse)
def query_agent(request: AgentRequest) -> AgentResponse:
    """Run a job search and return the agent's final text response."""
    try:
        result = run_job_agent(request.prompt)
        content = result["messages"][-1].content
        if isinstance(content, str):
            answer = content
        else:
            answer = "\n".join(
                block if isinstance(block, str) else block["text"]
                for block in content
                if isinstance(block, str)
                or (isinstance(block, dict) and block.get("type") == "text")
            )
        if not answer.strip():
            raise ValueError("Agent returned no text")
        return AgentResponse(answer=answer)
    except JobStorageError as exc:
        logger.error("Job persistence failed")
        raise HTTPException(
            status_code=503, detail="Unable to save jobs. Please try again later."
        ) from exc
    except Exception as exc:
        # Do not expose upstream errors, credentials or prompts in the response.
        logger.error("Agent request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Agent 暂时无法完成请求，请稍后重试。"
        ) from exc

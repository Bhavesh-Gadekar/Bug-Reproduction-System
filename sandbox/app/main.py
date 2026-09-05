"""FastAPI application for the sandbox runner service.

Single endpoint: POST /run
  - Accepts a JobRequest (base_image, command, timeout_seconds, env)
  - Executes the command inside a hardened Docker container
  - Returns a JobResult (stdout, stderr, exit_code, duration_seconds, timed_out)

Heavy execution is offloaded to a thread-pool executor so FastAPI's event
loop is never blocked while a container is running.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from app.config import Settings, get_settings
from app.runner import JobRequest, JobResult, run_job

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Thread-pool for blocking Docker calls
# ──────────────────────────────────────────────────────────────────────────────
# Limit concurrency: each slot corresponds to one running container.  Adjust
# MAX_WORKERS to match the host's available CPU / memory head-room.
MAX_WORKERS = 4
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="sandbox-worker")

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────────────


class RunRequest(BaseModel):
    """Payload accepted by POST /run."""

    base_image: str = Field(
        ...,
        description="Docker image tag to run (e.g. 'python:3.11-slim')",
        examples=["python:3.11-slim"],
    )
    command: list[str] = Field(
        ...,
        description="Command and arguments to execute inside the container",
        examples=[["python", "-c", "print('hello')"]],
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Wall-clock timeout for the container (1–120 s)",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Additional environment variables to inject into the container",
    )
    mounts: list[str] = Field(
        default_factory=list,
        description="Volumes or host directories to mount into the container (scoped :ro by default)",
    )
    workdir: str | None = Field(
        default=None,
        description="Working directory inside the container",
    )

    @field_validator("base_image")
    @classmethod
    def image_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("base_image must not be empty")
        return v.strip()

    @field_validator("command")
    @classmethod
    def command_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("command must not be empty")
        return v


class RunResponse(BaseModel):
    """Response returned by POST /run."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool
    container_id: str


# ──────────────────────────────────────────────────────────────────────────────
# Application
# ──────────────────────────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description=(
        "Secure Docker container execution service. "
        "Runs arbitrary commands inside hardened, isolated containers "
        "and returns stdout / stderr / exit-code / duration."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — always returns 200 if the service is up."""
    return {"status": "healthy", "service": "sandbox-runner"}


@app.post(
    "/run",
    response_model=RunResponse,
    tags=["Execution"],
    summary="Run a command inside a hardened Docker container",
    responses={
        200: {"description": "Command completed (check exit_code for success/failure)"},
        400: {"description": "Invalid request payload"},
        503: {"description": "Docker is unavailable on the host"},
    },
)
async def run_command(
    body: RunRequest,
    cfg: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    """
    Execute *body.command* inside a fresh Docker container built from
    *body.base_image* with the following security profile:

    - `--network=none` (full network isolation)
    - `--read-only` root filesystem + writable `/tmp` tmpfs
    - `--cap-drop=ALL`
    - `--security-opt=no-new-privileges`
    - CPU, memory, and PID limits from service config
    - Dual timeout: subprocess deadline + watchdog thread
    """
    if body.timeout_seconds > cfg.MAX_TIMEOUT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"timeout_seconds ({body.timeout_seconds}) exceeds the "
                f"configured maximum ({cfg.MAX_TIMEOUT_SECONDS} s)"
            ),
        )

    job = JobRequest(
        base_image=body.base_image,
        command=body.command,
        timeout_seconds=body.timeout_seconds,
        env=body.env,
        mounts=body.mounts,
        workdir=body.workdir,
    )

    loop = asyncio.get_event_loop()
    try:
        result: JobResult = await loop.run_in_executor(
            _executor,
            run_job,
            job,
            cfg,
        )
    except FileNotFoundError as exc:
        # docker CLI not found in PATH inside the sandbox service container
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker CLI not found. Is the Docker socket mounted?",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error running job: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Container execution failed: {exc}",
        ) from exc

    return RunResponse(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_seconds=result.duration_seconds,
        timed_out=result.timed_out,
        container_id=result.container_id,
    )

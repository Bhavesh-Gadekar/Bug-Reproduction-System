"""Database connection, LangGraph checkpointer factory, and telemetry persistence for worker.

Provides an async context manager `get_checkpointer()` that sets up an
`AsyncPostgresSaver` backed by a psycopg connection pool connected to Neon.
Also provides independent schema definitions and persistence helpers for
reproduction_runs and run_steps.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from app.core.config import get_worker_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Independent schema definitions for reproduction_runs and run_steps.
#
# NOTE: These table definitions MUST be kept in sync manually with
# api/alembic/versions/0001_initial_schema.py if that schema changes,
# since there is no shared source of truth between the api and worker services.
# This is a deliberate architectural tradeoff for service independence.
# ---------------------------------------------------------------------------

metadata = sa.MetaData()

reproduction_runs_table = sa.Table(
    "reproduction_runs",
    metadata,
    sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
    sa.Column("bug_report_id", PG_UUID(as_uuid=True), nullable=False),
    sa.Column("status", sa.String(50), nullable=False, server_default="queued"),
    sa.Column("model_version", sa.String(100), nullable=True),
    sa.Column("prompt_version", sa.String(100), nullable=True),
    sa.Column("candidate_produced", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("plausible_reproduced", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("sandbox_container_id", sa.String(255), nullable=True),
)

run_steps_table = sa.Table(
    "run_steps",
    metadata,
    sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", PG_UUID(as_uuid=True), nullable=False),
    sa.Column("node_name", sa.String(255), nullable=False),
    sa.Column("input", JSONB, nullable=True),
    sa.Column("output", JSONB, nullable=True),
    sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
)


def _safe_uuid(val: str | uuid.UUID | None) -> uuid.UUID:
    """Convert string to UUID, generating a deterministic UUID5 if not standard format."""
    if isinstance(val, uuid.UUID):
        return val
    if not val:
        return uuid.uuid4()
    try:
        return uuid.UUID(val)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(val))


def ensure_reproduction_run(
    run_id: str | uuid.UUID,
    bug_report_id: str | uuid.UUID,
    model_version: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """
    Ensure the parent reproduction_runs row exists before recording run_steps.

    Gracefully logs a warning if database connection is unavailable.
    """
    settings = get_worker_settings()
    if not settings.NEON_DATABASE_URL:
        return

    run_uuid = _safe_uuid(run_id)
    bug_report_uuid = _safe_uuid(bug_report_id)

    try:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            stmt = sa.text(
                """
                INSERT INTO reproduction_runs (
                    id,
                    bug_report_id,
                    status,
                    model_version,
                    prompt_version,
                    started_at
                ) VALUES (
                    :id,
                    :bug_report_id,
                    'queued',
                    :model_version,
                    :prompt_version,
                    :started_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    model_version = COALESCE(EXCLUDED.model_version, reproduction_runs.model_version),
                    prompt_version = COALESCE(EXCLUDED.prompt_version, reproduction_runs.prompt_version)
                """
            )
            conn.execute(
                stmt,
                {
                    "id": run_uuid,
                    "bug_report_id": bug_report_uuid,
                    "model_version": model_version,
                    "prompt_version": prompt_version,
                    "started_at": datetime.now(tz=timezone.utc),
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not ensure reproduction_runs row for %s: %s", run_id, exc)


def log_run_step(
    run_id: str | uuid.UUID,
    node_name: str,
    input_data: dict[str, Any] | None = None,
    output_data: dict[str, Any] | None = None,
    tokens_used: int = 0,
    latency_ms: int = 0,
) -> None:
    """
    Insert a step execution record into the run_steps table.

    Captures prompt_version, model_version, tokens, and latency.
    Gracefully logs a warning if database connection is unavailable.
    """
    settings = get_worker_settings()
    if not settings.NEON_DATABASE_URL:
        return

    run_uuid = _safe_uuid(run_id)
    step_id = uuid.uuid4()

    try:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            stmt = sa.insert(run_steps_table).values(
                id=step_id,
                run_id=run_uuid,
                node_name=node_name,
                input=input_data or {},
                output=output_data or {},
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                created_at=datetime.now(tz=timezone.utc),
            )
            conn.execute(stmt)
            logger.info("Logged run_step for node=%s run_id=%s (latency=%dms)", node_name, run_id, latency_ms)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not log run_step for node=%s run_id=%s: %s", node_name, run_id, exc)


@contextlib.asynccontextmanager
async def get_checkpointer() -> AsyncIterator[Any]:
    """
    Yield an initialized AsyncPostgresSaver connected to Neon Postgres.

    Creates checkpointer tables on first run via `await checkpointer.setup()`.
    """
    settings = get_worker_settings()
    dsn = settings.neon_pg_dsn

    if not dsn:
        raise ValueError("NEON_DATABASE_URL is not configured.")

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
    except ImportError as err:
        raise RuntimeError(
            "langgraph-checkpoint-postgres and psycopg_pool must be installed "
            "to use get_checkpointer()."
        ) from err

    async with AsyncConnectionPool(conninfo=dsn, max_size=10, kwargs={"autocommit": True}) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer

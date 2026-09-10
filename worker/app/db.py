"""Database connection, LangGraph checkpointer factory, and telemetry persistence for worker.

Provides an async context manager `get_checkpointer()` that sets up an
`AsyncPostgresSaver` backed by a psycopg connection pool connected to Neon.
Also provides independent schema definitions and persistence helpers for
reproduction_runs and run_steps.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
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
    sa.Column("persist_error", sa.Text, nullable=True),
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

artifacts_table = sa.Table(
    "artifacts",
    metadata,
    sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
    sa.Column("run_id", PG_UUID(as_uuid=True), nullable=False),
    sa.Column("type", sa.String(50), nullable=False),
    sa.Column("storage_path", sa.Text, nullable=False),
    sa.Column("status", sa.String(50), nullable=False, server_default="uploaded"),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
)

worker_incidents_table = sa.Table(
    "worker_incidents",
    metadata,
    sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("exception_type", sa.String(255), nullable=False),
    sa.Column("exception_message", sa.Text, nullable=True),
    sa.Column("traceback", sa.Text, nullable=False),
    sa.Column("in_flight_run_ids", JSONB, nullable=False),
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


def record_artifact(
    run_id: str | uuid.UUID,
    artifact_type: str,
    storage_path: str,
    status: str = "uploaded",
    error: str | None = None,
) -> uuid.UUID | None:
    """
    Insert a record into the artifacts table in Neon DB.
    """
    settings = get_worker_settings()
    if not settings.NEON_DATABASE_URL:
        return None

    run_uuid = _safe_uuid(run_id)
    artifact_id = uuid.uuid4()

    try:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            stmt = sa.text(
                """
                INSERT INTO artifacts (id, run_id, type, storage_path, status, error, created_at)
                VALUES (:id, :run_id, CAST(:type AS artifact_type), :storage_path, :status, :error, :created_at)
                """
            )
            conn.execute(
                stmt,
                {
                    "id": artifact_id,
                    "run_id": run_uuid,
                    "type": artifact_type,
                    "storage_path": storage_path,
                    "status": status,
                    "error": error,
                    "created_at": datetime.now(tz=timezone.utc),
                },
            )
            logger.info("Recorded artifact type=%s path=%s status=%s for run_id=%s", artifact_type, storage_path, status, run_id)
            return artifact_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not record artifact for run_id=%s: %s", run_id, exc)
        return None


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


def update_run_status(
    run_id: str | uuid.UUID,
    status: str,
    completed: bool = False,
    persist_error: str | None = None,
) -> None:
    """Update the status of a reproduction_run in Neon DB."""
    settings = get_worker_settings()
    if not settings.NEON_DATABASE_URL:
        return

    # Normalize status to valid reproduction_run_status enum
    normalized_status = {
        "running": "executing",
        "completed": "succeeded",
        "error": "error",
    }.get(status.lower(), status.lower())

    run_uuid = _safe_uuid(run_id)
    try:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            if completed:
                if persist_error is not None:
                    stmt = sa.text(
                        "UPDATE reproduction_runs SET status = CAST(:status AS reproduction_run_status), persist_error = :persist_error, completed_at = :completed_at WHERE id = :id"
                    )
                    conn.execute(stmt, {"id": run_uuid, "status": normalized_status, "persist_error": persist_error, "completed_at": datetime.now(tz=timezone.utc)})
                else:
                    stmt = sa.text(
                        "UPDATE reproduction_runs SET status = CAST(:status AS reproduction_run_status), completed_at = :completed_at WHERE id = :id"
                    )
                    conn.execute(stmt, {"id": run_uuid, "status": normalized_status, "completed_at": datetime.now(tz=timezone.utc)})
            else:
                if persist_error is not None:
                    stmt = sa.text(
                        "UPDATE reproduction_runs SET status = CAST(:status AS reproduction_run_status), persist_error = :persist_error WHERE id = :id"
                    )
                    conn.execute(stmt, {"id": run_uuid, "status": normalized_status, "persist_error": persist_error})
                else:
                    stmt = sa.text(
                        "UPDATE reproduction_runs SET status = CAST(:status AS reproduction_run_status) WHERE id = :id"
                    )
                    conn.execute(stmt, {"id": run_uuid, "status": normalized_status})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not update reproduction_runs status for %s to %s: %s", run_id, status, exc)


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

    async with AsyncConnectionPool(
        conninfo=dsn,
        max_size=10,
        max_idle=30.0,
        check=AsyncConnectionPool.check_connection,
        kwargs={"autocommit": True},
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer


_incident_lock = threading.Lock()
_recorded_incident_keys: set[str] = set()
DEAD_LETTER_INCIDENT_DIR = Path("/tmp/dead_letter_incidents")


def record_worker_incident(
    exception: BaseException,
    tb_str: str,
    in_flight_run_ids: list[str] | None = None,
    worker_started_at: datetime | None = None,
) -> uuid.UUID | None:
    """
    Record an unhandled worker crash incident using an independent, synchronous
    psycopg2 connection directly to Neon DB.

    If the database is unreachable, falls back to the dead-letter file mechanism.
    Guarded by an atomic lock and deduplication check to prevent duplicate entries.
    """
    import json
    with _incident_lock:
        incident_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        exc_type = (
            f"{type(exception).__module__}.{type(exception).__qualname__}"
            if getattr(type(exception), "__module__", "builtins") != "builtins"
            else type(exception).__qualname__
        )
        exc_msg = str(exception)
        run_ids = in_flight_run_ids or []

        dedup_key = f"{exc_type}:{exc_msg}:{','.join(sorted(run_ids))}"
        if dedup_key in _recorded_incident_keys:
            logger.info("Incident %s already recorded; skipping duplicate.", dedup_key)
            return None
        _recorded_incident_keys.add(dedup_key)

        settings = get_worker_settings()
        payload = {
            "id": str(incident_id),
            "started_at": worker_started_at.isoformat() if worker_started_at else None,
            "detected_at": now.isoformat(),
            "exception_type": exc_type,
            "exception_message": exc_msg,
            "traceback": tb_str,
            "in_flight_run_ids": run_ids,
        }

        # 1. Attempt synchronous write via independent direct DB connection (psycopg3 / psycopg2)
        db_written = False
        if settings.NEON_DATABASE_URL:
            try:
                conn = None
                try:
                    import psycopg
                    conn = psycopg.connect(settings.neon_pg_dsn, autocommit=True, connect_timeout=5)
                except ImportError:
                    import psycopg2
                    conn = psycopg2.connect(settings.NEON_DATABASE_URL, connect_timeout=5)
                    conn.autocommit = True

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO worker_incidents (
                                id, started_at, detected_at, exception_type,
                                exception_message, traceback, in_flight_run_ids, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(incident_id),
                                worker_started_at,
                                now,
                                exc_type,
                                exc_msg,
                                tb_str,
                                json.dumps(run_ids),
                                now,
                            ),
                        )
                    if hasattr(conn, "commit") and not getattr(conn, "autocommit", False):
                        conn.commit()
                    db_written = True
                    logger.error(
                        "CRITICAL: Recorded worker crash incident %s (type=%s, in_flight=%s) to worker_incidents table.",
                        incident_id,
                        exc_type,
                        run_ids,
                    )
                finally:
                    if conn:
                        conn.close()
            except Exception as db_exc:  # noqa: BLE001
                logger.error("CRITICAL: Failed to write worker incident to Neon DB: %s", db_exc)

        # 2. If DB write failed or was not configured, spill over to dead-letter disk storage
        if not db_written:
            try:
                DEAD_LETTER_INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
                dl_file = DEAD_LETTER_INCIDENT_DIR / f"incident_{incident_id}.json"
                with open(dl_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                logger.critical(
                    "CRITICAL: Spillover worker incident written to dead-letter file %s",
                    dl_file,
                )
            except Exception as dl_exc:  # noqa: BLE001
                logger.critical(
                    "CRITICAL: Failed even to write worker incident to dead-letter file: %s",
                    dl_exc,
                )

        return incident_id

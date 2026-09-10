"""[Persist Artifacts + Report] node — write results to Neon + B2.

Writes / updates the ``reproduction_runs`` row in Neon via SQLAlchemy.
B2 blob upload is stubbed (logged only) to keep the worker runnable without
B2 credentials in CI; the real upload is wired in a later step.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_worker_settings
from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


async def persist_node(state: BugReportState) -> dict[str, Any]:
    """
    Persist run metadata to Neon and artifact blobs to B2.

    * Neon write: attempted if ``NEON_DATABASE_URL`` is set. On failure,
      marks the run status as "error" with persist_error details so failures
      are never silent.
    * B2 upload: uploads scripts and logs. On failure or missing credentials,
      marks the specific artifact as "upload_failed" in DB and returns
      detailed artifact summaries.

    Always returns a non-empty ``final_verdict`` so callers can check the
    terminal state.
    """
    import time
    start_time = time.monotonic()
    settings = get_worker_settings()

    terminal_verdict = (
        state.final_verdict
        or ("infra_error" if (state.last_execution_record and state.last_execution_record.verdict == "infra_error") else ("succeeded" if state.reproduced else "failed"))
    )

    # ------------------------------------------------------------------
    # B2 artifact upload — performed before terminal DB update so artifacts exist
    # ------------------------------------------------------------------
    artifact_summaries = _upload_b2_artifacts(state, settings)

    # ------------------------------------------------------------------
    # Neon DB write — updates reproduction_runs to terminal status
    # ------------------------------------------------------------------
    persist_error: str | None = None
    if settings.NEON_DATABASE_URL:
        try:
            await _write_to_neon(state, terminal_verdict, settings)
        except Exception as exc:  # noqa: BLE001
            persist_error = str(exc)
            terminal_verdict = "error"
            logger.exception("Failed to persist run to Neon: %s", exc)
            try:
                await _record_persist_failure(state, persist_error, settings)
            except Exception as inner_exc:  # noqa: BLE001
                logger.critical(
                    "CRITICAL: Failed even to record persist error status in Neon after retries: %s. Spilling over to dead-letter storage.",
                    inner_exc,
                )
                _write_dead_letter_record(state, persist_error, str(inner_exc))
    else:
        logger.warning(
            "NEON_DATABASE_URL not set — skipping DB persist for bug_report_id=%s",
            state.bug_report_id,
        )

    try:
        from app.db import log_run_step
        run_id = state.run_id or state.bug_report_id
        step_status = "error" if persist_error else "completed"
        log_run_step(
            run_id=run_id,
            node_name="persist",
            input_data={"terminal_verdict": terminal_verdict, "reproduced": state.reproduced},
            output_data={
                "status": step_status,
                "final_verdict": terminal_verdict,
                "persist_error": persist_error,
                "attempts": state.hypothesis_index,
                "artifacts": artifact_summaries,
            },
            latency_ms=max(int((time.monotonic() - start_time) * 1000), 1),
        )
    except Exception as log_exc:  # noqa: BLE001
        logger.warning("Could not log persist run_step to Neon: %s", log_exc)

    logger.info(
        "Run complete: bug_report_id=%s reproduced=%s verdict=%s persist_error=%s attempts=%d",
        state.bug_report_id,
        state.reproduced,
        terminal_verdict,
        persist_error,
        state.hypothesis_index,
    )

    return {
        "final_verdict": terminal_verdict,
        "persist_error": persist_error,
        "artifacts": artifact_summaries,
    }


async def _write_to_neon(
    state: BugReportState,
    verdict: str,
    settings: Any,
) -> None:
    """
    Upsert the ``reproduction_runs`` row for this bug report.

    Uses a raw SQL upsert so we don't need to replicate the full ORM model
    inside the worker package.
    """
    import sqlalchemy as sa
    from app.db import _safe_uuid

    dsn = settings.neon_sa_url
    engine = sa.create_engine(dsn, pool_pre_ping=True)

    run_uuid = _safe_uuid(state.run_id)
    bug_report_uuid = _safe_uuid(state.bug_report_id)

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO reproduction_runs (
                    id,
                    bug_report_id,
                    status,
                    model_version,
                    prompt_version,
                    candidate_produced,
                    plausible_reproduced,
                    persist_error,
                    started_at,
                    completed_at,
                    sandbox_container_id
                ) VALUES (
                    :id,
                    :bug_report_id,
                    CAST(:status AS reproduction_run_status),
                    :model_version,
                    :prompt_version,
                    :candidate_produced,
                    :plausible_reproduced,
                    :persist_error,
                    :started_at,
                    :completed_at,
                    :sandbox_container_id
                )
                ON CONFLICT (id) DO UPDATE SET
                    status               = EXCLUDED.status,
                    model_version        = EXCLUDED.model_version,
                    prompt_version       = EXCLUDED.prompt_version,
                    candidate_produced   = EXCLUDED.candidate_produced,
                    plausible_reproduced = EXCLUDED.plausible_reproduced,
                    persist_error        = EXCLUDED.persist_error,
                    -- Preserve started_at set by ingest_node; only overwrite if NULL
                    started_at           = COALESCE(reproduction_runs.started_at, EXCLUDED.started_at),
                    completed_at         = EXCLUDED.completed_at,
                    sandbox_container_id = COALESCE(EXCLUDED.sandbox_container_id, reproduction_runs.sandbox_container_id)
                """
            ),
            {
                "id": run_uuid,
                "bug_report_id": bug_report_uuid,
                "status": "infra_error" if verdict == "infra_error" else ("error" if (state.error or verdict == "error") else ("succeeded" if state.reproduced else "failed")),
                "model_version": getattr(state, "model_version", None) or settings.GEMINI_MODEL,
                "prompt_version": getattr(state, "prompt_version", None) or "v1",
                "candidate_produced": bool(state.current_script),
                "plausible_reproduced": state.reproduced,
                "persist_error": state.persist_error or state.error or None,
                # started_at: use value from state if ingest_node set it; fall back to now()
                "started_at": getattr(state, "started_at", None) or datetime.now(tz=timezone.utc),
                "completed_at": datetime.now(tz=timezone.utc),
                "sandbox_container_id": getattr(state, "sandbox_container_id", None) or None,
            },
        )

    logger.info("Persisted run to Neon for bug_report_id=%s run_id=%s", state.bug_report_id, state.run_id)


async def _record_persist_failure(
    state: BugReportState,
    error_msg: str,
    settings: Any,
    max_retries: int = 3,
) -> None:
    """Fallback writer to mark reproduction_runs row as 'error' with persist_error with retries."""
    import asyncio
    import sqlalchemy as sa
    from app.db import _safe_uuid

    dsn = settings.neon_sa_url
    engine = sa.create_engine(dsn, pool_pre_ping=True)

    run_uuid = _safe_uuid(state.run_id)
    bug_report_uuid = _safe_uuid(state.bug_report_id)

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO reproduction_runs (
                            id,
                            bug_report_id,
                            status,
                            persist_error,
                            completed_at
                        ) VALUES (
                            :id,
                            :bug_report_id,
                            CAST('error' AS reproduction_run_status),
                            :persist_error,
                            :completed_at
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            status        = CAST('error' AS reproduction_run_status),
                            persist_error = EXCLUDED.persist_error,
                            completed_at  = EXCLUDED.completed_at
                        """
                    ),
                    {
                        "id": run_uuid,
                        "bug_report_id": bug_report_uuid,
                        "persist_error": error_msg,
                        "completed_at": datetime.now(tz=timezone.utc),
                    },
                )
            logger.info("Successfully recorded persist error to Neon on attempt %d", attempt)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            engine.dispose()
            logger.warning("Attempt %d/%d to record persist failure to Neon failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                await asyncio.sleep(0.5 * attempt)

    if last_exc:
        raise last_exc


def _write_dead_letter_record(state: BugReportState, error: str, inner_error: str | None = None) -> Any:
    """Write run state and error info to local dead-letter storage when DB is completely unreachable."""
    import json
    from pathlib import Path

    dead_letter_dir = Path("/tmp/dead_letter_runs")
    dead_letter_dir.mkdir(parents=True, exist_ok=True)
    run_id = state.run_id or state.bug_report_id
    dead_letter_file = dead_letter_dir / f"{run_id}.json"

    data = {
        "run_id": state.run_id,
        "bug_report_id": state.bug_report_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "reproduced": state.reproduced,
        "persist_error": error,
        "db_record_failure_error": inner_error,
        "current_script": state.current_script,
        "attempts": state.hypothesis_index,
    }

    dead_letter_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.critical("DEAD LETTER: Persisted failure record to disk at %s", dead_letter_file)
    return dead_letter_file


def _upload_b2_artifacts(state: BugReportState, settings: Any) -> list[dict[str, Any]]:
    """
    Upload reproduction artifacts (scripts and logs) to Backblaze B2 and record in DB.

    If B2 credentials are missing or an upload fails, records the artifact in DB with
    status="upload_failed" and the error message, and returns the list of artifact summaries.
    """
    from app.db import record_artifact

    run_id = state.run_id or state.bug_report_id
    artifacts_summary: list[dict[str, Any]] = []

    def _handle_artifact(art_type: str, key: str, body: bytes, content_type: str, s3_client: Any) -> None:
        if s3_client is None:
            err = "B2 credentials not configured or S3 client initialization failed"
            record_artifact(run_id=run_id, artifact_type=art_type, storage_path=key, status="upload_failed", error=err)
            artifacts_summary.append({
                "type": art_type,
                "storage_path": key,
                "status": "upload_failed",
                "error": err,
            })
            return

        try:
            s3_client.put_object(
                Bucket=settings.B2_BUCKET_NAME,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
            record_artifact(run_id=run_id, artifact_type=art_type, storage_path=key, status="uploaded")
            logger.info("Uploaded artifact to B2: s3://%s/%s", settings.B2_BUCKET_NAME, key)
            artifacts_summary.append({
                "type": art_type,
                "storage_path": key,
                "status": "uploaded",
                "error": None,
            })
        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            logger.error("Failed to upload artifact to B2 (%s): %s", key, exc)
            record_artifact(run_id=run_id, artifact_type=art_type, storage_path=key, status="upload_failed", error=err_msg)
            artifacts_summary.append({
                "type": art_type,
                "storage_path": key,
                "status": "upload_failed",
                "error": err_msg,
            })

    s3 = None
    if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY:
        import boto3
        from botocore.config import Config
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=settings.B2_ENDPOINT,
                aws_access_key_id=settings.B2_KEY_ID,
                aws_secret_access_key=settings.B2_APPLICATION_KEY,
                config=Config(signature_version="s3v4"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to initialize boto3 S3 client: %s", exc)
            s3 = None
    else:
        logger.warning("B2 credentials not configured — marking live artifacts as upload_failed for bug_report_id=%s", state.bug_report_id)

    # 1. Repro script artifact
    if state.current_script:
        key = f"artifacts/{state.bug_report_id}/repro_script.py"
        _handle_artifact("repro_script", key, state.current_script.encode("utf-8"), "text/x-python", s3)

    # 2. Minimized script artifact (if minimized)
    if state.minimized_script and state.minimized_script != state.current_script:
        key = f"artifacts/{state.bug_report_id}/minimized_script.py"
        _handle_artifact("repro_script", key, state.minimized_script.encode("utf-8"), "text/x-python", s3)

    # 3. Execution logs
    for record in state.execution_history:
        if record.stdout or record.stderr:
            key = f"artifacts/{state.bug_report_id}/attempt_{record.hypothesis_index}_log.txt"
            content = f"--- ATTEMPT {record.hypothesis_index} ---\nExit Code: {record.exit_code}\nVerdict: {record.verdict}\n\n--- STDOUT ---\n{record.stdout}\n\n--- STDERR ---\n{record.stderr}\n"
            _handle_artifact("log", key, content.encode("utf-8"), "text/plain", s3)

    return artifacts_summary

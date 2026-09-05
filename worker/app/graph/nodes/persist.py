"""[Persist Artifacts + Report] node — write results to Neon + B2.

Writes / updates the ``reproduction_runs`` row in Neon via SQLAlchemy.
B2 blob upload is stubbed (logged only) to keep the worker runnable without
B2 credentials in CI; the real upload is wired in a later step.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


async def persist_node(state: BugReportState) -> dict[str, Any]:
    """
    Persist run metadata to Neon and artifact blobs to B2.

    * Neon write: attempted if ``NEON_DATABASE_URL`` is set; skipped with a
      warning otherwise (keeps tests offline-safe).
    * B2 upload: stubbed — logs the artifact paths that *would* be uploaded.

    Always returns a non-empty ``final_verdict`` so callers can check the
    terminal state.
    """
    from app.core.config import get_worker_settings

    settings = get_worker_settings()

    terminal_verdict = (
        state.final_verdict
        or ("succeeded" if state.reproduced else "failed")
    )

    # ------------------------------------------------------------------
    # Neon DB write
    # ------------------------------------------------------------------
    if settings.NEON_DATABASE_URL:
        try:
            await _write_to_neon(state, terminal_verdict, settings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist run to Neon: %s", exc)
    else:
        logger.warning(
            "NEON_DATABASE_URL not set — skipping DB persist for bug_report_id=%s",
            state.bug_report_id,
        )

    # ------------------------------------------------------------------
    # B2 artifact upload
    # ------------------------------------------------------------------
    _upload_b2_artifacts(state, settings)

    logger.info(
        "Run complete: bug_report_id=%s reproduced=%s verdict=%s attempts=%d",
        state.bug_report_id,
        state.reproduced,
        terminal_verdict,
        state.hypothesis_index,
    )

    return {"final_verdict": terminal_verdict}


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
                    candidate_produced,
                    plausible_reproduced,
                    completed_at
                ) VALUES (
                    :id,
                    :bug_report_id,
                    :status,
                    :candidate_produced,
                    :plausible_reproduced,
                    :completed_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    status               = EXCLUDED.status,
                    candidate_produced   = EXCLUDED.candidate_produced,
                    plausible_reproduced = EXCLUDED.plausible_reproduced,
                    completed_at         = EXCLUDED.completed_at
                """
            ),
            {
                "id": run_uuid,
                "bug_report_id": bug_report_uuid,
                "status": "succeeded" if state.reproduced else "failed",
                "candidate_produced": bool(state.current_script),
                "plausible_reproduced": state.reproduced,
                "completed_at": datetime.now(tz=timezone.utc),
            },
        )

    logger.info("Persisted run to Neon for bug_report_id=%s run_id=%s", state.bug_report_id, state.run_id)


def _upload_b2_artifacts(state: BugReportState, settings: Any) -> None:
    """Upload reproduction artifacts (scripts and logs) to Backblaze B2 and record in DB."""
    if not (settings.B2_KEY_ID and settings.B2_APPLICATION_KEY):
        logger.warning("B2 credentials not configured — skipping live B2 upload for bug_report_id=%s", state.bug_report_id)
        return

    import boto3
    from botocore.config import Config
    from app.db import record_artifact

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.B2_ENDPOINT,
            aws_access_key_id=settings.B2_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            config=Config(signature_version="s3v4"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize boto3 S3 client: %s", exc)
        return

    bucket = settings.B2_BUCKET_NAME
    run_id = state.run_id or state.bug_report_id

    # 1. Repro script artifact
    if state.current_script:
        key = f"artifacts/{state.bug_report_id}/repro_script.py"
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=state.current_script.encode("utf-8"),
                ContentType="text/x-python",
            )
            record_artifact(run_id=run_id, artifact_type="repro_script", storage_path=key)
            logger.info("Uploaded reproduction script to B2: s3://%s/%s", bucket, key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upload repro script to B2 (%s): %s", key, exc)

    # 2. Minimized script artifact (if minimized)
    if state.minimized_script and state.minimized_script != state.current_script:
        key = f"artifacts/{state.bug_report_id}/minimized_script.py"
        try:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=state.minimized_script.encode("utf-8"),
                ContentType="text/x-python",
            )
            record_artifact(run_id=run_id, artifact_type="repro_script", storage_path=key)
            logger.info("Uploaded minimized script to B2: s3://%s/%s", bucket, key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upload minimized script to B2 (%s): %s", key, exc)

    # 3. Execution logs
    for idx, record in enumerate(state.execution_history):
        if record.stdout or record.stderr:
            key = f"artifacts/{state.bug_report_id}/attempt_{record.hypothesis_index}_log.txt"
            content = f"--- ATTEMPT {record.hypothesis_index} ---\nExit Code: {record.exit_code}\nVerdict: {record.verdict}\n\n--- STDOUT ---\n{record.stdout}\n\n--- STDERR ---\n{record.stderr}\n"
            try:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=content.encode("utf-8"),
                    ContentType="text/plain",
                )
                record_artifact(run_id=run_id, artifact_type="log", storage_path=key)
                logger.info("Uploaded execution log to B2: s3://%s/%s", bucket, key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to upload execution log to B2 (%s): %s", key, exc)

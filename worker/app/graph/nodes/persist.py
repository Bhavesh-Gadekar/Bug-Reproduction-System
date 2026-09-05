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
    # B2 artifact upload (stubbed)
    # ------------------------------------------------------------------
    _stub_b2_upload(state)

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


def _stub_b2_upload(state: BugReportState) -> None:
    """Log what *would* be uploaded to B2 (real upload wired in next step)."""
    artifacts = []
    if state.current_script:
        artifacts.append(f"repro_script/{state.bug_report_id}.py")
    if state.minimized_script:
        artifacts.append(f"minimized_script/{state.bug_report_id}_min.py")
    for i, record in enumerate(state.execution_history):
        artifacts.append(f"logs/{state.bug_report_id}/attempt_{i}_stdout.txt")

    logger.info(
        "[B2 STUB] Would upload %d artifact(s) for bug_report_id=%s: %s",
        len(artifacts),
        state.bug_report_id,
        artifacts,
    )

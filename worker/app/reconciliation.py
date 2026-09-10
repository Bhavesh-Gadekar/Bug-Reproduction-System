"""Dead-letter run reconciliation mechanism for Bug Reproduction System.

Scans /tmp/dead_letter_runs/*.json and writes terminal status="error" + persist_error
back to the corresponding reproduction_runs row in Neon when connectivity is restored.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from app.core.config import get_worker_settings
from app.db import _safe_uuid, log_run_step

logger = logging.getLogger(__name__)

DEFAULT_DEAD_LETTER_DIR = Path("/tmp/dead_letter_runs")


async def reconcile_dead_letter_runs(
    settings: Any = None,
    dead_letter_dir: Path | str = DEFAULT_DEAD_LETTER_DIR,
) -> list[dict[str, Any]]:
    """Scan dead-letter directory and reconcile orphaned runs into Neon DB.

    For each dead-letter JSON record:
    1. Read the run metadata and persist failure error.
    2. Attempt to write terminal status="error" and persist_error to Neon DB.
    3. If successful, log telemetry step and delete the dead-letter file.
    4. If the write fails (e.g. Neon still down), leave the file for the next retry.
    """
    settings = settings or get_worker_settings()
    if not settings.NEON_DATABASE_URL:
        logger.debug("NEON_DATABASE_URL not configured; skipping dead-letter reconciliation.")
        return []

    dead_dir = Path(dead_letter_dir)
    if not dead_dir.exists() or not dead_dir.is_dir():
        logger.debug("Dead-letter directory %s does not exist; nothing to reconcile.", dead_dir)
        return []

    dead_files = sorted(list(dead_dir.glob("*.json")))
    if not dead_files:
        return []

    logger.info("Found %d dead-letter run record(s) in %s. Attempting reconciliation...", len(dead_files), dead_dir)
    reconciled_runs: list[dict[str, Any]] = []

    dsn = settings.neon_sa_url
    engine = sa.create_engine(dsn, pool_pre_ping=True)

    for dead_file in dead_files:
        try:
            content = dead_file.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as read_exc:
            logger.error("Failed to read dead-letter file %s: %s", dead_file, read_exc)
            continue

        raw_run_id = data.get("run_id")
        raw_bug_id = data.get("bug_report_id")
        if not raw_run_id:
            logger.warning("Dead-letter file %s missing run_id; skipping.", dead_file)
            continue

        run_uuid = _safe_uuid(raw_run_id)
        bug_report_uuid = _safe_uuid(raw_bug_id) if raw_bug_id else run_uuid
        persist_err = data.get("persist_error") or "Neon connectivity severed during persist"
        reconciled_persist_error = f"[RECOVERED FROM DEAD-LETTER] {persist_err}"
        current_script = data.get("current_script")
        reproduced = bool(data.get("reproduced", False))

        try:
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
                            persist_error,
                            completed_at
                        ) VALUES (
                            :id,
                            :bug_report_id,
                            CAST('error' AS reproduction_run_status),
                            :candidate_produced,
                            :plausible_reproduced,
                            :persist_error,
                            :completed_at
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            status               = CAST('error' AS reproduction_run_status),
                            candidate_produced   = EXCLUDED.candidate_produced,
                            plausible_reproduced = EXCLUDED.plausible_reproduced,
                            persist_error        = EXCLUDED.persist_error,
                            completed_at         = EXCLUDED.completed_at
                        """
                    ),
                    {
                        "id": run_uuid,
                        "bug_report_id": bug_report_uuid,
                        "candidate_produced": bool(current_script),
                        "plausible_reproduced": reproduced,
                        "persist_error": reconciled_persist_error,
                        "completed_at": datetime.now(tz=timezone.utc),
                    },
                )

            # Telemetry logging for the reconciliation step
            try:
                log_run_step(
                    run_id=raw_run_id,
                    node_name="dead_letter_reconciled",
                    input_data={"dead_letter_file": str(dead_file), "original_timestamp": data.get("timestamp")},
                    output_data={
                        "status": "reconciled",
                        "final_verdict": "error",
                        "persist_error": reconciled_persist_error,
                        "script_recovered": bool(current_script),
                        "attempts": data.get("attempts", 0),
                    },
                    latency_ms=10,
                )
            except Exception as step_exc:
                logger.warning("Could not log dead_letter_reconciled step: %s", step_exc)

            # Successfully written to Neon — remove the dead-letter file
            dead_file.unlink(missing_ok=True)
            logger.info("Successfully reconciled dead-letter run %s from %s into Neon DB", raw_run_id, dead_file)
            reconciled_runs.append({
                "run_id": str(raw_run_id),
                "status": "reconciled",
                "file": str(dead_file),
                "persist_error": reconciled_persist_error,
            })
        except Exception as write_exc:
            logger.warning(
                "Failed to reconcile dead-letter file %s to Neon (database may still be unreachable): %s",
                dead_file,
                write_exc,
            )
            # Leave file on disk for retry next cycle

    engine.dispose()
    return reconciled_runs

"""[Ingest Bug Report] node — validates and normalises the initial state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graph.state import BugReportState


async def ingest_node(state: BugReportState) -> dict[str, Any]:
    """
    Entry point for every run.

    * Sets ``started_at`` to the current UTC time.
    * Normalises ``raw_stack_trace`` (strip leading/trailing whitespace).
    * Validates that required fields are non-empty; writes ``error`` if not.
    """
    errors: list[str] = []

    if not state.bug_report_id:
        errors.append("bug_report_id is required")
    if not state.raw_stack_trace.strip():
        errors.append("raw_stack_trace must not be empty")
    if not state.repo.git_url:
        errors.append("repo.git_url is required")

    if errors:
        return {
            "error": "; ".join(errors),
            "final_verdict": "invalid_input",
            "started_at": datetime.now(tz=timezone.utc),
        }

    import uuid
    from app.db import ensure_reproduction_run

    run_id = state.run_id or str(uuid.uuid4())
    ensure_reproduction_run(run_id=run_id, bug_report_id=state.bug_report_id)

    return {
        "run_id": run_id,
        "started_at": datetime.now(tz=timezone.utc),
        "raw_stack_trace": state.raw_stack_trace.strip(),
        # Ensure max_hypotheses respects the ceiling from settings (callers
        # may override it in the state — ingest clamps it to a safe max).
        "max_hypotheses": min(state.max_hypotheses, 10),
    }

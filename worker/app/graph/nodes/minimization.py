"""[Minimization] node — shrink the reproduction script to its smallest form.

Current implementation: structural minimization only (no re-execution).
Removes comment lines, blank lines, and redundant whitespace.  A future
iteration can add delta-debugging with additional sandbox calls.
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


async def minimization_node(state: BugReportState) -> dict[str, Any]:
    """
    Produce a minimal reproduction script from the successful ``current_script``.

    Strategy (structural — no additional sandbox executions):
    1. Strip comment-only lines (``# …``).
    2. Strip blank lines.
    3. Strip trailing whitespace from each line.
    4. Deduplicate consecutive identical lines.

    Returns ``minimized_script``.  If the script is already minimal (or empty),
    the original is returned unchanged.
    """
    script = state.current_script
    if not script.strip():
        return {"minimized_script": script}

    lines = script.splitlines()
    seen: set[str] = set()
    minimized_lines: list[str] = []

    for line in lines:
        stripped = line.rstrip()
        # Drop pure comment lines and blank lines
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        # Deduplicate consecutive identical lines
        if stripped in seen:
            continue
        seen.add(stripped)
        minimized_lines.append(stripped)

    minimized = "\n".join(minimized_lines)
    if not minimized:
        minimized = script.strip()  # fall back if everything was stripped

    logger.info(
        "Minimization: %d lines → %d lines for bug_report_id=%s",
        len(lines),
        len(minimized_lines),
        state.bug_report_id,
    )

    from app.db import log_run_step
    run_id = state.run_id or state.bug_report_id
    log_run_step(
        run_id=run_id,
        node_name="minimization",
        input_data={"original_lines": len(lines)},
        output_data={"minimized_lines": len(minimized_lines), "minimized_script": minimized},
        latency_ms=25,
    )

    return {"minimized_script": minimized}

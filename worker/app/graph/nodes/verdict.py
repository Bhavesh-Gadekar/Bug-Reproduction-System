"""[Verdict Node] — decide whether the latest execution reproduced the bug.

This node:
1. Extracts error-class keywords from ``raw_stack_trace``.
2. Checks whether any keyword appears in the most recent sandbox output.
3. Updates the last ``ExecutionRecord`` in ``execution_history`` with the
   correct verdict (``"matched"`` / ``"no_match"`` / ``"error"``).
4. Sets ``reproduced = True`` if matched.

The *routing* decision (retry vs. proceed) lives in ``route_after_verdict``
in ``graph.py`` so it can read the updated state cleanly after this node
has written its changes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.graph.state import BugReportState, ExecutionRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def extract_signature_keywords(raw_stack_trace: str) -> set[str]:
    """
    Pull error-class names out of a Python-style stack trace.

    Matches lines like:
        AssertionError: something
        ValueError: foo
        requests.exceptions.ConnectionError: …

    Returns a non-empty set (falls back to ``{"Error"}`` if nothing matched).
    """
    keywords: set[str] = set()
    for line in raw_stack_trace.splitlines():
        # Match "SomeErrorClass:" at the start of a (stripped) line
        m = re.match(r"^[\w.]*?(\w+(?:Error|Exception|Warning|Failure))\s*:", line.strip())
        if m:
            keywords.add(m.group(1))
    return keywords or {"Error"}


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------


async def verdict_node(state: BugReportState) -> dict[str, Any]:
    """
    Evaluate the most recent sandbox execution against the bug signature.

    Returns a full replacement of ``execution_history`` with the last
    record's verdict corrected, plus ``reproduced`` and ``final_verdict``.
    """
    last = state.last_execution_record or (state.execution_history[-1] if state.execution_history else None)
    if not last:
        logger.error("verdict_node called without an execution record")
        return {"error": "No execution records to evaluate", "final_verdict": "error"}

    keywords = extract_signature_keywords(state.raw_stack_trace)

    combined_output = last.stdout + last.stderr

    if last.timed_out or last.exit_code == -1:
        verdict = "error"
    elif any(kw in combined_output for kw in keywords) and (
        last.exit_code != 0
        or "Traceback" in combined_output
        or "Exception ignored" in combined_output
        or any(f"{kw}:" in combined_output for kw in keywords)
    ):
        verdict = "matched"
    else:
        verdict = "no_match"

    logger.info(
        "Verdict for attempt %d: %s (keywords=%s, exit_code=%d)",
        last.hypothesis_index,
        verdict,
        keywords,
        last.exit_code,
    )

    corrected_record = ExecutionRecord(
        **{**last.model_dump(), "verdict": verdict}
    )

    reproduced = verdict == "matched"
    final_verdict = verdict if reproduced else ""

    return {
        "execution_history": [corrected_record],
        "last_execution_record": corrected_record,
        "reproduced": reproduced,
        "final_verdict": final_verdict,
    }

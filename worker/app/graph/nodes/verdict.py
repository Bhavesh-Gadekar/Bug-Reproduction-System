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


def extract_primary_error(raw_stack_trace: str, title: str = "", description: str = "") -> str | None:
    """
    Extract the primary (top-level) reported exception from a stack trace or bug report.

    In Python tracebacks with chained exceptions (e.g. 'During handling of the above exception...'
    or 'The above exception was the direct cause...'), the final exception at the bottom of the
    trace is the top-level unhandled crash being reported. Preceding exceptions are intermediate
    causes and must not be treated as the primary reported bug.
    """
    exceptions: list[str] = []
    for line in raw_stack_trace.splitlines():
        m = re.search(r"^[\w.]*?(\w+(?:Error|Exception|Warning|Failure))\s*:", line.strip())
        if m:
            exceptions.append(m.group(1))

    if exceptions:
        return exceptions[-1]

    # Fallback: check title and description for explicit exception names
    title_desc = f"{title} {description}"
    m_title = re.findall(r"\b([A-Z]\w*(?:Error|Exception|Warning|Failure))\b", title_desc)
    if m_title:
        return m_title[0]

    return None


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
        m = re.search(r"^[\w.]*?(\w+(?:Error|Exception|Warning|Failure))\s*:", line.strip())
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
    import time
    start_time = time.monotonic()

    last = state.last_execution_record or (state.execution_history[-1] if state.execution_history else None)
    if not last:
        logger.error("verdict_node called without an execution record")
        return {"error": "No execution records to evaluate", "final_verdict": "error"}

    keywords = extract_signature_keywords(state.raw_stack_trace)
    primary_error = extract_primary_error(
        state.raw_stack_trace,
        title=getattr(state, "title", "") or "",
        description=getattr(state, "description", "") or "",
    )

    combined_output = last.stdout + last.stderr

    infra_failure_patterns = [
        "failed to connect to the docker api",
        "dockerdesktoplinuxengine",
        "is the docker daemon running",
        "cannot connect to the docker daemon",
        "error during connect",
        "docker cli not found",
        "docker: error during connect",
    ]
    is_infra_error = (
        last.verdict == "infra_error"
        or any(p in combined_output.lower() for p in infra_failure_patterns)
    )

    if is_infra_error:
        verdict = "infra_error"
    elif last.timed_out or last.exit_code == -1:
        verdict = "error"
    else:
        # Determine if the execution reproduced the reported bug:
        # 1. If a primary exception was identified from the bug report / trace,
        #    it MUST be present in the sandbox execution output as an exception.
        #    Incidental intermediate causes (e.g. IllegalMonthError in a dateutil trace
        #    where TypeError was the reported bug) do NOT qualify as a reproduction.
        # 2. If no primary exception could be isolated, fall back to requiring any keyword.
        has_error_signature = (
            last.exit_code != 0
            or "Traceback" in combined_output
            or "Exception ignored" in combined_output
        )

        if has_error_signature:
            if primary_error:
                primary_pattern = r"(?:^|\s|[\w.]*?\.)" + re.escape(primary_error) + r"\s*:"
                if re.search(primary_pattern, combined_output, re.MULTILINE) or f"{primary_error}:" in combined_output:
                    verdict = "matched"
                else:
                    verdict = "no_match"
            elif any(kw in combined_output for kw in keywords):
                verdict = "matched"
            else:
                verdict = "no_match"
        else:
            verdict = "no_match"

    logger.info(
        "Verdict for attempt %d: %s (primary_error=%s, keywords=%s, exit_code=%d)",
        last.hypothesis_index,
        verdict,
        primary_error,
        keywords,
        last.exit_code,
    )

    corrected_record = ExecutionRecord(
        **{**last.model_dump(), "verdict": verdict}
    )

    reproduced = verdict == "matched"
    if verdict == "infra_error":
        final_verdict = "infra_error"
    else:
        final_verdict = verdict if reproduced else ""

    from app.db import log_run_step
    run_id = state.run_id or state.bug_report_id
    latency_ms = max(int((time.monotonic() - start_time) * 1000), 1)
    log_run_step(
        run_id=run_id,
        node_name="verdict",
        input_data={"attempt": last.hypothesis_index, "exit_code": last.exit_code},
        output_data={
            "verdict": verdict,
            "reproduced": reproduced,
            "attempt": last.hypothesis_index,
        },
        latency_ms=latency_ms,
    )

    ret_dict: dict[str, Any] = {
        "execution_history": [corrected_record],
        "last_execution_record": corrected_record,
        "reproduced": reproduced,
        "final_verdict": final_verdict,
    }
    if verdict == "infra_error":
        ret_dict["error"] = f"Infrastructure error: {last.stderr.strip()[:500]}"

    return ret_dict

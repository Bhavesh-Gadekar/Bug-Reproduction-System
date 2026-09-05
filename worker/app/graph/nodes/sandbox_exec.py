"""[Sandbox Execution] node — run the current script in an isolated container.

Makes a real HTTP POST to the sandbox service (``http://sandbox:8001/run``).
In tests, the ``SandboxClient`` is replaced by ``FakeSandboxClient`` so no
Docker daemon is needed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.graph.state import ExecutionRecord

if TYPE_CHECKING:
    from app.graph.sandbox import SandboxClient
    from app.graph.state import BugReportState

logger = logging.getLogger(__name__)

# Default timeout forwarded to the sandbox service if not in settings.
_DEFAULT_TIMEOUT = 60


def make_sandbox_exec_node(sandbox: "SandboxClient", timeout_seconds: int = _DEFAULT_TIMEOUT):
    """
    Return an async LangGraph node that executes the current script.

    The script is passed as ``python3 -c <script>`` inside the chosen
    ``base_image``.  The result is appended to ``execution_history`` with a
    preliminary verdict of ``"error"``; the real verdict is assigned by the
    subsequent ``verdict`` node.
    """

    async def sandbox_exec_node(state: "BugReportState") -> dict[str, Any]:
        script = state.current_script
        base_image = state.base_image or "python:3.11-slim"

        logger.info(
            "Executing script (attempt %d) for bug_report_id=%s via sandbox",
            state.hypothesis_index,
            state.bug_report_id,
        )

        try:
            result = await sandbox.run(
                base_image=base_image,
                command=["python3", "-c", script],
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sandbox call failed: %s", exc)
            record = ExecutionRecord(
                hypothesis_index=state.hypothesis_index,
                hypothesis=state.current_hypothesis,
                script=script,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_seconds=0.0,
                timed_out=False,
                verdict="error",
            )
            return {"last_execution_record": record}

        record = ExecutionRecord(
            hypothesis_index=state.hypothesis_index,
            hypothesis=state.current_hypothesis,
            script=script,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
            verdict="error",
        )

        logger.info(
            "Sandbox returned exit_code=%d, timed_out=%s for attempt %d",
            result.exit_code,
            result.timed_out,
            state.hypothesis_index,
        )

        return {"last_execution_record": record}

    return sandbox_exec_node

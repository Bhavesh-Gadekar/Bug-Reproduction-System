"""[Sandbox Execution] node — run the current script in an isolated container.

Makes a real HTTP POST to the sandbox service (``http://sandbox:8001/run``).
In tests, the ``SandboxClient`` is replaced by ``FakeSandboxClient`` so no
Docker daemon is needed.
"""

from __future__ import annotations

import logging
from pathlib import Path
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

        # Determine sandbox mount configuration for the cloned repository
        mounts: list[str] = []
        workdir: str | None = None
        env: dict[str, str] = {}

        from app.core.config import get_worker_settings
        settings = get_worker_settings()

        if state.repo.volume_name == settings.REPOS_VOLUME_NAME or (state.repo.volume_name and Path("/repos").is_dir()):
            mounts = [f"{settings.REPOS_VOLUME_NAME}:/repos:ro"]
            repo_path = f"/repos/{state.bug_report_id}"
            workdir = repo_path
            env = {"PYTHONPATH": f"{repo_path}/.deps:{repo_path}/src:{repo_path}"}
        elif state.repo.local_path:
            clean_local_path = Path(state.repo.local_path).resolve().as_posix()
            mounts = [f"{clean_local_path}:/workspace:ro"]
            workdir = "/workspace"
            env = {"PYTHONPATH": "/workspace/.deps:/workspace/src:/workspace"}

        try:
            result = await sandbox.run(
                base_image=base_image,
                command=["python3", "-c", script],
                timeout_seconds=timeout_seconds,
                mounts=mounts,
                workdir=workdir,
                env=env,
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

        # Check if exit was due to Docker infrastructure/daemon failure
        infra_failure_patterns = [
            "failed to connect to the docker api",
            "dockerdesktoplinuxengine",
            "is the docker daemon running",
            "cannot connect to the docker daemon",
            "error during connect",
            "docker cli not found",
            "docker: error during connect",
            "error response from daemon",
            "not a valid windows path",
        ]
        stderr_lower = (result.stderr or "").lower()
        is_infra_error = result.exit_code == 125 or any(p in stderr_lower for p in infra_failure_patterns)

        initial_verdict = "infra_error" if is_infra_error else "error"

        record = ExecutionRecord(
            hypothesis_index=state.hypothesis_index,
            hypothesis=state.current_hypothesis,
            script=script,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
            verdict=initial_verdict,
            container_id=result.container_id,
        )

        logger.info(
            "Sandbox returned container_id=%s, exit_code=%d, timed_out=%s, infra_error=%s for attempt %d",
            result.container_id,
            result.exit_code,
            result.timed_out,
            is_infra_error,
            state.hypothesis_index,
        )

        from app.db import log_run_step
        run_id = state.run_id or state.bug_report_id
        log_run_step(
            run_id=run_id,
            node_name="sandbox_exec",
            input_data={"attempt": state.hypothesis_index, "base_image": base_image},
            output_data={
                "exit_code": result.exit_code,
                "stdout": result.stdout[:2000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "duration_seconds": result.duration_seconds,
                "timed_out": result.timed_out,
                "container_id": result.container_id,
                "is_infra_error": is_infra_error,
            },
            latency_ms=int(result.duration_seconds * 1000),
        )

        update_dict: dict[str, Any] = {
            "last_execution_record": record,
            "sandbox_container_id": result.container_id,
        }
        if is_infra_error:
            update_dict["final_verdict"] = "infra_error"
            update_dict["error"] = f"Infrastructure error: {result.stderr.strip()}"

        return update_dict

    return sandbox_exec_node

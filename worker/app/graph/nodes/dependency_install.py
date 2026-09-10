"""[Dependency Installation] node — installs repository dependencies into .deps directory."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from app.db import log_run_step, update_run_status
from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


def _get_repo_dir(state: BugReportState) -> Path:
    """Resolve the directory where the repository was cloned."""
    if state.repo.local_path and Path(state.repo.local_path).is_dir():
        return Path(state.repo.local_path)
    base_repos = Path("/repos")
    if base_repos.is_dir():
        slug = state.bug_report_id or "default_repo"
        target = base_repos / slug
        if target.is_dir():
            return target
    fallback = Path("/tmp/repos") / (state.bug_report_id or "default_repo")
    return fallback


async def dependency_install_node(state: BugReportState) -> dict[str, Any]:
    """
    Install repository dependencies into a localized `.deps` directory.

    Executed after repo_analysis and env_setup, before hypothesis generation
    and sandbox execution. Any failure is logged loudly into run_steps and
    updates reproduction_runs status to 'error'.
    """
    run_id = state.run_id or state.bug_report_id
    repo_dir = _get_repo_dir(state)
    lang = (state.repo.language or "python").lower()

    if not repo_dir.is_dir():
        logger.warning("Repo dir %s not found for dependency installation.", repo_dir)
        log_run_step(
            run_id=run_id,
            node_name="dependency_install",
            input_data={"repo_dir": str(repo_dir), "language": lang},
            output_data={"skipped": True, "reason": "repo_dir_missing"},
            latency_ms=0,
        )
        return {}

    deps_dir = repo_dir / ".deps"
    deps_dir.mkdir(parents=True, exist_ok=True)

    commands_to_run: list[list[str]] = []

    if lang == "python":
        # 1. Check requirements.txt
        req_file = repo_dir / "requirements.txt"
        if req_file.exists():
            commands_to_run.append([
                sys.executable, "-m", "pip", "install",
                "--prefer-binary",
                "--target", str(deps_dir),
                "-r", str(req_file),
            ])

        # 2. Check setup.py / pyproject.toml / setup.cfg
        if (repo_dir / "setup.py").exists() or (repo_dir / "pyproject.toml").exists() or (repo_dir / "setup.cfg").exists():
            commands_to_run.append([
                sys.executable, "-m", "pip", "install",
                "--prefer-binary",
                "--target", str(deps_dir),
                str(repo_dir),
            ])

    if not commands_to_run:
        logger.info("No install manifest found for %s. Skipping dependency install.", repo_dir)
        log_run_step(
            run_id=run_id,
            node_name="dependency_install",
            input_data={"repo_dir": str(repo_dir), "language": lang},
            output_data={"skipped": True, "reason": "no_install_manifest"},
            latency_ms=10,
        )
        return {}

    combined_stdout = ""
    combined_stderr = ""
    total_latency_ms = 0

    for cmd in commands_to_run:
        cmd_str = " ".join(cmd)
        logger.info("Running dependency install command: %s", cmd_str)
        t_start = time.time()
        try:
            res = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(repo_dir),
                env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
            )
            elapsed_ms = int((time.time() - t_start) * 1000)
            total_latency_ms += elapsed_ms
            combined_stdout += f"=== {cmd_str} ===\n{res.stdout}\n"
            combined_stderr += f"=== {cmd_str} ===\n{res.stderr}\n"

            if res.returncode != 0:
                logger.error(
                    "Dependency installation failed for run %s (code %d): %s",
                    run_id,
                    res.returncode,
                    res.stderr.strip(),
                )
                # Log loudly to run_steps
                log_run_step(
                    run_id=run_id,
                    node_name="dependency_install",
                    input_data={"command": cmd_str, "repo_dir": str(repo_dir)},
                    output_data={
                        "exit_code": res.returncode,
                        "command": cmd_str,
                        "stdout": combined_stdout[:2000],
                        "stderr": combined_stderr[:2000],
                        "error": "Non-zero exit code during dependency installation",
                    },
                    latency_ms=total_latency_ms,
                )
                # Mark run in DB loudly as error
                error_msg = f"Dependency installation failed (code {res.returncode}): {res.stderr[:300]}"
                update_run_status(
                    run_id=run_id,
                    status="error",
                    completed=True,
                    persist_error=error_msg,
                )
                return {
                    "error": error_msg,
                    "persist_error": error_msg,
                }

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - t_start) * 1000)
            total_latency_ms += elapsed_ms
            error_msg = f"Dependency installation timed out after 180s: {cmd_str}"
            logger.error(error_msg)
            log_run_step(
                run_id=run_id,
                node_name="dependency_install",
                input_data={"command": cmd_str, "repo_dir": str(repo_dir)},
                output_data={
                    "exit_code": -1,
                    "command": cmd_str,
                    "stdout": combined_stdout[:2000],
                    "stderr": "Command timed out",
                    "error": error_msg,
                },
                latency_ms=total_latency_ms,
            )
            update_run_status(
                run_id=run_id,
                status="error",
                completed=True,
                persist_error=error_msg,
            )
            return {
                "error": error_msg,
                "persist_error": error_msg,
            }

    # All commands succeeded
    logger.info("Dependencies installed successfully into %s in %dms", deps_dir, total_latency_ms)
    log_run_step(
        run_id=run_id,
        node_name="dependency_install",
        input_data={"commands": [" ".join(c) for c in commands_to_run], "deps_dir": str(deps_dir)},
        output_data={
            "exit_code": 0,
            "stdout": combined_stdout[:2000],
            "stderr": combined_stderr[:2000],
            "installed_deps_dir": str(deps_dir),
        },
        latency_ms=total_latency_ms,
    )
    return {}

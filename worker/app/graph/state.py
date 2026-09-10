"""Typed state shared across every node in the bug-reproduction LangGraph.

LangGraph merges the *dict* returned by each node into the current state.
List fields annotated with ``operator.add`` as reducer are *appended* to
rather than replaced — this is how ``execution_history`` accumulates records
across retry iterations without any node needing to read-and-rewrite the full
list.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class RepoMeta(BaseModel):
    """Metadata about the repository under test."""

    git_url: str
    branch: str = "main"
    base_commit_sha: str | None = None
    fix_commit_sha: str | None = None
    local_path: str | None = None      # Local clone filesystem path
    volume_name: str | None = None     # Docker volume name or mount source
    language: str | None = None        # e.g. "python", "typescript", "java"
    framework: str | None = None       # e.g. "pytest", "jest", "junit"
    build_system: str | None = None    # e.g. "pip", "npm", "maven"


class ExecutionRecord(BaseModel):
    """Immutable record of a single sandbox execution attempt."""

    hypothesis_index: int
    hypothesis: str
    script: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    verdict: Literal["matched", "no_match", "error", "infra_error"]
    container_id: str = ""


# ---------------------------------------------------------------------------
# Primary state model
# ---------------------------------------------------------------------------


class BugReportState(BaseModel):
    """
    Full mutable state threaded through the bug-reproduction graph.

    Scalar fields (str, int, bool) are replaced on each update.
    ``execution_history`` uses ``operator.add`` so each node can append a
    single record without touching the rest of the list.
    """

    # ------------------------------------------------------------------
    # Identity — set once at ingest, never mutated
    # ------------------------------------------------------------------
    bug_report_id: str
    workspace_id: str
    run_id: str = ""

    # ------------------------------------------------------------------
    # Input payload
    # ------------------------------------------------------------------
    title: str
    description: str
    raw_stack_trace: str

    # ------------------------------------------------------------------
    # Repo context — populated by repo_analysis and env_setup
    # ------------------------------------------------------------------
    repo: RepoMeta
    base_image: str = ""
    install_command: str = ""

    # ------------------------------------------------------------------
    # LLM outputs for the current iteration
    # Overwritten on each retry cycle.
    # ------------------------------------------------------------------
    current_hypothesis: str = ""
    current_script: str = ""

    # ------------------------------------------------------------------
    # Iteration counters
    # ``hypothesis_index`` is incremented inside hypothesis_gen so that
    # every retry produces a distinct checkpoint key.
    # ------------------------------------------------------------------
    hypothesis_index: int = 0
    max_hypotheses: int = 5

    # ------------------------------------------------------------------
    # Execution history — append-only via operator.add reducer
    # ------------------------------------------------------------------
    last_execution_record: ExecutionRecord | None = None
    execution_history: Annotated[list[ExecutionRecord], operator.add] = Field(
        default_factory=list
    )
    sandbox_container_id: str = ""

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------
    token_budget: int = 50_000
    tokens_used: int = 0
    time_budget_seconds: int = 600
    started_at: datetime | None = None

    # ------------------------------------------------------------------
    # Terminal state — written by verdict / minimization / persist
    # ------------------------------------------------------------------
    reproduced: bool = False
    minimized_script: str = ""
    final_verdict: str = ""
    error: str = ""
    persist_error: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    checkpointer_type: str = ""
    checkpointer_degraded: bool = False


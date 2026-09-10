"""Pydantic schemas for bug report submission and reproduction runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class RepoInput(BaseModel):
    """Input metadata for the repository containing the bug."""
    git_url: str = Field(..., description="Git repository clone URL")
    branch: str = Field(default="main", description="Git branch name")
    base_commit_sha: Optional[str] = Field(default=None, description="Base commit SHA before fix")
    fix_commit_sha: Optional[str] = Field(default=None, description="Fix commit SHA")
    language: Optional[str] = Field(default=None, description="Language override")
    framework: Optional[str] = Field(default=None, description="Test framework override")
    build_system: Optional[str] = Field(default=None, description="Build system override")


class BugReportCreate(BaseModel):
    """Payload for submitting a new bug report to reproduce."""
    title: str = Field(..., min_length=1, max_length=500, description="Bug title / summary")
    description: Optional[str] = Field(default=None, description="Detailed explanation of the issue")
    raw_stack_trace: str = Field(..., min_length=1, description="Raw error traceback or exception message")
    repo: RepoInput = Field(..., description="Target repository details")
    workspace_id: Optional[uuid.UUID] = Field(default=None, description="Workspace ID (inferred from auth if omitted)")
    max_hypotheses: int = Field(default=5, ge=1, le=10, description="Maximum hypothesis attempts")
    reported_env: Optional[dict[str, Any]] = Field(default=None, description="Environment details (OS, Python version)")


class BugReportSubmissionResponse(BaseModel):
    """Response returned when a bug report is enqueued."""
    bug_report_id: uuid.UUID
    run_id: uuid.UUID
    status: str
    stream_url: str
    message: str = "Bug reproduction task successfully enqueued."


class RunStepResponse(BaseModel):
    """Execution step detail in a reproduction run."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    node_name: str
    input: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None
    tokens_used: int = 0
    latency_ms: int = 0
    created_at: datetime


class ArtifactResponse(BaseModel):
    """Reproduction artifact item (script, log, diff)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    type: str
    storage_path: str
    created_at: datetime


class ReproductionRunDetailResponse(BaseModel):
    """Complete detail of a reproduction run including accumulated steps and artifacts."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bug_report_id: uuid.UUID
    status: str
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
    candidate_produced: bool = False
    plausible_reproduced: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    steps: list[RunStepResponse] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    bug_report: Optional[dict[str, Any]] = None

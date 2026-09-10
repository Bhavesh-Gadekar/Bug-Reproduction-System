"""Bug report endpoints for submitting and querying reproduction requests."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.redis import get_redis_pool
from app.db.session import get_db
from app.models.bug_report import BugReport
from app.models.enums import BugReportStatus, ReproductionRunStatus
from app.models.repo import Repo
from app.models.reproduction import ReproductionRun
from app.models.workspace import Workspace
from app.schemas.bug_report import BugReportCreate, BugReportSubmissionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bug-reports", tags=["Bug Reports"])


def _get_or_create_workspace(db: Session, target_id: uuid.UUID | None = None) -> Workspace:
    """Ensure a valid Workspace exists for foreign key constraints."""
    if target_id:
        ws = db.execute(select(Workspace).where(Workspace.id == target_id)).scalar_one_or_none()
        if ws:
            return ws

    # Look for any existing workspace
    ws = db.execute(select(Workspace).limit(1)).scalar_one_or_none()
    if ws:
        return ws

    # Create default workspace
    ws = Workspace(
        id=target_id or uuid.uuid4(),
        name="Default Workspace",
    )
    db.add(ws)
    db.flush()
    return ws


def _get_or_create_repo(db: Session, workspace_id: uuid.UUID, git_url: str, branch: str = "main") -> Repo:
    """Find or create target repository under the workspace."""
    repo = db.execute(
        select(Repo).where(
            Repo.workspace_id == workspace_id,
            Repo.git_url == git_url,
        )
    ).scalar_one_or_none()

    if not repo:
        repo = Repo(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            git_url=git_url,
            default_branch=branch or "main",
        )
        db.add(repo)
        db.flush()
    return repo


@router.post(
    "",
    response_model=BugReportSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a bug report for reproduction",
    description="Validates bug report details, persists DB records, and enqueues reproduction task in Redis + Arq queue.",
)
async def submit_bug_report(
    payload: BugReportCreate,
    db: Session = Depends(get_db),
) -> Any:
    """Ingest bug report, persist initial entities, and enqueue async reproduction job."""
    # 1. Resolve workspace
    workspace = _get_or_create_workspace(db, payload.workspace_id)
    workspace_id = workspace.id

    # 2. Resolve repository
    repo = _get_or_create_repo(
        db=db,
        workspace_id=workspace_id,
        git_url=payload.repo.git_url,
        branch=payload.repo.branch,
    )

    # 3. Create BugReport record
    bug_report_id = uuid.uuid4()
    bug_report = BugReport(
        id=bug_report_id,
        workspace_id=workspace_id,
        repo_id=repo.id,
        title=payload.title,
        description=payload.description,
        raw_stack_trace=payload.raw_stack_trace,
        reported_env=payload.reported_env,
        status=BugReportStatus.QUEUED,
    )
    db.add(bug_report)

    # 4. Create initial ReproductionRun record
    run_id = uuid.uuid4()
    reproduction_run = ReproductionRun(
        id=run_id,
        bug_report_id=bug_report_id,
        status=ReproductionRunStatus.QUEUED,
    )
    db.add(reproduction_run)
    db.commit()

    # 5. Build task payload for LangGraph worker
    task_payload = {
        "bug_report_id": str(bug_report_id),
        "workspace_id": str(workspace_id),
        "run_id": str(run_id),
        "title": payload.title,
        "description": payload.description or "",
        "raw_stack_trace": payload.raw_stack_trace,
        "repo": {
            "git_url": payload.repo.git_url,
            "branch": payload.repo.branch or "main",
            "base_commit_sha": payload.repo.base_commit_sha,
            "fix_commit_sha": payload.repo.fix_commit_sha,
            "language": payload.repo.language,
            "framework": payload.repo.framework,
            "build_system": payload.repo.build_system,
        },
        "max_hypotheses": payload.max_hypotheses,
    }

    # 6. Enqueue task via Arq
    redis_pool = await get_redis_pool()
    job_id = None
    if redis_pool is not None:
        try:
            job = await redis_pool.enqueue_job(
                "run_reproduction_task",
                task_payload,
                _job_id=f"repro-{run_id}",
                _queue_name="reproduction_tasks",
            )
            job_id = job.job_id if job else str(run_id)
            logger.info("Enqueued reproduction task %s for run %s", job_id, run_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not enqueue Arq job to Redis: %s. Continuing with persisted run.", exc)
    else:
        logger.warning("Redis pool unavailable — job saved in DB with status 'queued'.")

    return BugReportSubmissionResponse(
        bug_report_id=bug_report_id,
        run_id=run_id,
        status="queued",
        stream_url=f"/api/runs/{run_id}/stream",
        message="Bug report accepted. Reproduction task enqueued.",
    )


@router.get(
    "/{bug_report_id}",
    summary="Get bug report details",
)
def get_bug_report(
    bug_report_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve bug report information and its associated runs."""
    bug_report = db.execute(
        select(BugReport).where(BugReport.id == bug_report_id)
    ).scalar_one_or_none()

    if not bug_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bug report {bug_report_id} not found",
        )

    runs = db.execute(
        select(ReproductionRun)
        .where(ReproductionRun.bug_report_id == bug_report_id)
        .order_by(ReproductionRun.started_at.desc().nullslast())
    ).scalars().all()

    return {
        "id": str(bug_report.id),
        "workspace_id": str(bug_report.workspace_id),
        "repo_id": str(bug_report.repo_id),
        "title": bug_report.title,
        "description": bug_report.description,
        "raw_stack_trace": bug_report.raw_stack_trace,
        "status": bug_report.status.value if hasattr(bug_report.status, "value") else str(bug_report.status),
        "created_at": bug_report.created_at.isoformat() if bug_report.created_at else None,
        "runs": [
            {
                "id": str(r.id),
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ],
    }

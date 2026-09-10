"""Reproduction runs and SSE streaming endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db, get_session_factory
from app.models.bug_report import BugReport
from app.models.enums import ReproductionRunStatus
from app.models.reproduction import Artifact, ReproductionRun, RunStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["Reproduction Runs"])


TERMINAL_STATUSES = {
    ReproductionRunStatus.SUCCEEDED,
    ReproductionRunStatus.FAILED,
    ReproductionRunStatus.TIMED_OUT,
    ReproductionRunStatus.ERROR,
    ReproductionRunStatus.INFRA_ERROR,
    "succeeded",
    "failed",
    "timed_out",
    "completed",
    "error",
    "infra_error",
}


def _serialize_step(step: RunStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "run_id": str(step.run_id),
        "node_name": step.node_name,
        "input": step.input or {},
        "output": step.output or {},
        "tokens_used": step.tokens_used,
        "latency_ms": step.latency_ms,
        "created_at": step.created_at.isoformat() if step.created_at else None,
    }


def _serialize_artifact(art: Artifact) -> dict[str, Any]:
    return {
        "id": str(art.id),
        "run_id": str(art.run_id),
        "type": art.type.value if hasattr(art.type, "value") else str(art.type),
        "storage_path": art.storage_path,
        "status": getattr(art, "status", "uploaded"),
        "error": getattr(art, "error", None),
        "created_at": art.created_at.isoformat() if art.created_at else None,
    }


@router.get(
    "",
    summary="List reproduction runs",
    description="Retrieve paginated reproduction runs with staleness evaluation and filtering by raw_status and is_stale.",
)
def list_runs(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(default=15, ge=1, le=100, description="Items per page"),
    limit: int | None = Query(default=None, ge=1, le=100, description="Optional override for page_size"),
    offset: int | None = Query(default=None, ge=0, description="Optional explicit offset"),
    raw_status: str | None = Query(default=None, description="Filter by raw_status"),
    is_stale: bool | None = Query(default=None, description="Filter by staleness (True for stale only, False for non-stale only)"),
    stale_threshold_seconds: int = Query(default=300, ge=10, description="Seconds without activity before flagging non-terminal runs as stale"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    effective_limit = limit if limit is not None else page_size
    effective_offset = offset if offset is not None else (page - 1) * effective_limit

    steps_subq = (
        select(
            RunStep.run_id,
            func.max(RunStep.created_at).label("latest_act"),
            func.count(RunStep.id).label("step_count"),
        )
        .group_by(RunStep.run_id)
        .subquery()
    )
    artifacts_subq = (
        select(
            Artifact.run_id,
            func.count(Artifact.id).label("art_count"),
        )
        .group_by(Artifact.run_id)
        .subquery()
    )

    query = (
        select(
            ReproductionRun,
            BugReport.title.label("bug_title"),
            BugReport.description.label("bug_desc"),
            steps_subq.c.latest_act,
            steps_subq.c.step_count,
            artifacts_subq.c.art_count,
        )
        .outerjoin(BugReport, ReproductionRun.bug_report_id == BugReport.id)
        .outerjoin(steps_subq, ReproductionRun.id == steps_subq.c.run_id)
        .outerjoin(artifacts_subq, ReproductionRun.id == artifacts_subq.c.run_id)
        .order_by(ReproductionRun.started_at.desc().nullslast())
    )

    if raw_status:
        clean_status = raw_status.strip().lower()
        matched_enums = [e for e in ReproductionRunStatus if e.value.lower() == clean_status]
        if matched_enums:
            query = query.where(ReproductionRun.status.in_(matched_enums))
        else:
            query = query.where(ReproductionRun.status == clean_status)

    all_rows = db.execute(query).all()
    now = datetime.now(tz=timezone.utc)

    evaluated_items = []
    for row in all_rows:
        run = row[0]
        status_val = run.status.value if hasattr(run.status, "value") else str(run.status)

        run_is_stale = False
        run_stale_reason = None
        if status_val not in TERMINAL_STATUSES:
            last_activity = row.latest_act or run.started_at
            if not last_activity and hasattr(run, "created_at"):
                last_activity = run.created_at

            if last_activity:
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                elapsed_seconds = (now - last_activity).total_seconds()
                if elapsed_seconds >= stale_threshold_seconds:
                    run_is_stale = True
                    run_stale_reason = (
                        f"No activity detected for {int(elapsed_seconds)}s "
                        f"(exceeds {stale_threshold_seconds}s threshold while in non-terminal state '{status_val}')"
                    )

        if is_stale is not None and run_is_stale != is_stale:
            continue

        display_status = "stale" if run_is_stale else status_val

        evaluated_items.append({
            "id": str(run.id),
            "bug_report_id": str(run.bug_report_id),
            "status": display_status,
            "raw_status": status_val,
            "is_stale": run_is_stale,
            "stale_reason": run_stale_reason,
            "candidate_produced": run.candidate_produced,
            "plausible_reproduced": run.plausible_reproduced,
            "persist_error": getattr(run, "persist_error", None),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "model_version": run.model_version,
            "prompt_version": run.prompt_version,
            "step_count": row.step_count or 0,
            "artifact_count": row.art_count or 0,
            "bug_report": {
                "id": str(run.bug_report_id),
                "title": row.bug_title or "Untitled Bug Report",
                "description": row.bug_desc,
            }
            if row.bug_title
            else None,
        })

    total = len(evaluated_items)
    page_items = evaluated_items[effective_offset : effective_offset + effective_limit]

    return {
        "total": total,
        "page": page,
        "page_size": effective_limit,
        "items": page_items,
    }


@router.get(
    "/{run_id}",
    summary="Get reproduction run details and history",
)
def get_run_details(
    run_id: uuid.UUID,
    stale_threshold_seconds: int = Query(default=300, ge=10, description="Seconds without activity before flagging non-terminal runs as stale"),
    db: Session = Depends(get_db),
) -> Any:
    """Fetch complete run details including status, steps, and artifacts.

    If the run is in a non-terminal state and the last activity (from run_steps or
    started_at) is older than stale_threshold_seconds (default 300s / 5 min),
    it is flagged as stale (is_stale=True, status="stale") so monitoring and UI
    can distinguish stuck runs from active ones.
    """
    run = db.execute(
        select(ReproductionRun).where(ReproductionRun.id == run_id)
    ).scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reproduction run {run_id} not found",
        )

    bug_report = db.execute(
        select(BugReport).where(BugReport.id == run.bug_report_id)
    ).scalar_one_or_none()

    steps = db.execute(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.created_at.asc())
    ).scalars().all()

    artifacts = db.execute(
        select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
    ).scalars().all()

    status_val = run.status.value if hasattr(run.status, "value") else str(run.status)

    # Staleness evaluation for non-terminal runs
    is_stale = False
    stale_reason = None
    if status_val not in TERMINAL_STATUSES:
        last_activity_time = None
        if steps:
            last_activity_time = steps[-1].created_at
        if not last_activity_time and run.started_at:
            last_activity_time = run.started_at
        if not last_activity_time and hasattr(run, "created_at"):
            last_activity_time = run.created_at

        if last_activity_time:
            if last_activity_time.tzinfo is None:
                last_activity_time = last_activity_time.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            elapsed_seconds = (now - last_activity_time).total_seconds()
            if elapsed_seconds >= stale_threshold_seconds:
                is_stale = True
                stale_reason = (
                    f"No activity detected for {int(elapsed_seconds)}s "
                    f"(exceeds {stale_threshold_seconds}s threshold while in non-terminal state '{status_val}')"
                )

    display_status = "stale" if is_stale else status_val

    return {
        "id": str(run.id),
        "bug_report_id": str(run.bug_report_id),
        "status": display_status,
        "raw_status": status_val,
        "is_stale": is_stale,
        "stale_reason": stale_reason,
        "model_version": run.model_version,
        "prompt_version": run.prompt_version,
        "candidate_produced": run.candidate_produced,
        "plausible_reproduced": run.plausible_reproduced,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "sandbox_container_id": getattr(run, "sandbox_container_id", None),
        "persist_error": getattr(run, "persist_error", None),
        "steps": [_serialize_step(s) for s in steps],
        "artifacts": [_serialize_artifact(a) for a in artifacts],
        "bug_report": {
            "id": str(bug_report.id),
            "title": bug_report.title,
            "description": bug_report.description,
            "raw_stack_trace": bug_report.raw_stack_trace,
        }
        if bug_report
        else None,
    }


@router.get(
    "/{run_id}/artifacts",
    summary="Get reproduction run artifacts with signed download URLs",
)
def get_run_artifacts(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Any:
    """Fetch artifacts for a run and generate presigned download URLs if B2 credentials are set."""
    from app.core.config import get_settings
    settings = get_settings()

    artifacts = db.execute(
        select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
    ).scalars().all()

    s3_client = None
    if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY:
        import boto3
        from botocore.config import Config
        try:
            s3_client = boto3.client(
                "s3",
                endpoint_url=settings.B2_ENDPOINT,
                aws_access_key_id=settings.B2_KEY_ID,
                aws_secret_access_key=settings.B2_APPLICATION_KEY,
                config=Config(signature_version="s3v4"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not initialize S3 client for presigned URLs: %s", exc)

    results = []
    for art in artifacts:
        art_dict = _serialize_artifact(art)
        download_url = None
        if s3_client is not None and art_dict.get("status") != "upload_failed":
            try:
                download_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": settings.B2_BUCKET_NAME,
                        "Key": art.storage_path,
                    },
                    ExpiresIn=3600,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not generate presigned URL for %s: %s", art.storage_path, exc)
        art_dict["download_url"] = download_url
        results.append(art_dict)

    return {"run_id": str(run_id), "artifacts": results}


async def _run_steps_event_stream(
    run_id: uuid.UUID,
    request: Request,
    poll_interval_seconds: float = 1.0,
    stale_threshold_seconds: int = 300,
) -> AsyncGenerator[str, None]:
    """
    Generator streaming SSE events by polling Postgres run_steps and reproduction_runs.

    Yields:
      event: status -> current status of run
      event: step -> emitted for each new RunStep
      event: artifact -> emitted for each new Artifact
      event: done -> emitted when the run terminates
    """
    session_factory = get_session_factory()
    seen_step_ids: set[str] = set()
    seen_artifact_ids: set[str] = set()
    last_status: str | None = None

    logger.info("SSE client connected for run %s", run_id)

    try:
        while True:
            # Check client disconnection
            if await request.is_disconnected():
                logger.info("SSE client disconnected for run %s", run_id)
                break

            with session_factory() as db:
                run = db.execute(
                    select(ReproductionRun).where(ReproductionRun.id == run_id)
                ).scalar_one_or_none()

                if not run:
                    yield f"event: error\ndata: {json.dumps({'error': 'Run not found'})}\n\n"
                    break

                current_status = run.status.value if hasattr(run.status, "value") else str(run.status)

                # 1. Fetch current steps to check staleness and new events
                steps = db.execute(
                    select(RunStep)
                    .where(RunStep.run_id == run_id)
                    .order_by(RunStep.created_at.asc())
                ).scalars().all()

                is_stale = False
                stale_reason = None
                if current_status not in TERMINAL_STATUSES:
                    last_act = steps[-1].created_at if steps else run.started_at
                    if last_act:
                        if last_act.tzinfo is None:
                            last_act = last_act.replace(tzinfo=timezone.utc)
                        elapsed = (datetime.now(tz=timezone.utc) - last_act).total_seconds()
                        if elapsed >= stale_threshold_seconds:
                            is_stale = True
                            stale_reason = f"No activity for {int(elapsed)}s (exceeds {stale_threshold_seconds}s threshold)"

                effective_status = "stale" if is_stale else current_status

                # Emit status changes or staleness transitions
                if effective_status != last_status:
                    last_status = effective_status
                    status_payload = {
                        "run_id": str(run_id),
                        "status": effective_status,
                        "raw_status": current_status,
                        "is_stale": is_stale,
                        "stale_reason": stale_reason,
                        "candidate_produced": run.candidate_produced,
                        "plausible_reproduced": run.plausible_reproduced,
                        "persist_error": getattr(run, "persist_error", None),
                    }
                    yield f"event: status\ndata: {json.dumps(status_payload)}\n\n"

                for step in steps:
                    step_id_str = str(step.id)
                    if step_id_str not in seen_step_ids:
                        seen_step_ids.add(step_id_str)
                        step_data = _serialize_step(step)
                        yield f"event: step\ndata: {json.dumps(step_data)}\n\n"

                # 3. Fetch new artifacts
                artifacts = db.execute(
                    select(Artifact)
                    .where(Artifact.run_id == run_id)
                    .order_by(Artifact.created_at.asc())
                ).scalars().all()

                for art in artifacts:
                    art_id_str = str(art.id)
                    if art_id_str not in seen_artifact_ids:
                        seen_artifact_ids.add(art_id_str)
                        art_data = _serialize_artifact(art)
                        yield f"event: artifact\ndata: {json.dumps(art_data)}\n\n"

                # 4. If run reached terminal state, send terminal done event and exit
                if current_status in TERMINAL_STATUSES:
                    done_payload = {
                        "run_id": str(run_id),
                        "status": current_status,
                        "candidate_produced": run.candidate_produced,
                        "plausible_reproduced": run.plausible_reproduced,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "total_steps": len(seen_step_ids),
                        "persist_error": getattr(run, "persist_error", None),
                    }
                    yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                    logger.info("Run %s reached terminal state '%s'. Closing SSE stream.", run_id, current_status)
                    break

            await asyncio.sleep(poll_interval_seconds)

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for run %s", run_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in SSE stream for run %s: %s", run_id, exc)
        yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"


@router.get(
    "/{run_id}/stream",
    summary="SSE live stream for reproduction run steps",
    description="Streams Server-Sent Events (status, step, artifact, done) as the agent executes.",
    response_class=StreamingResponse,
)
async def stream_run_steps(
    run_id: uuid.UUID,
    request: Request,
    stale_threshold_seconds: int = Query(default=300, ge=10, description="Seconds without activity before flagging non-terminal runs as stale"),
) -> StreamingResponse:
    """Stream real-time reproduction steps and state progression via Server-Sent Events."""
    return StreamingResponse(
        _run_steps_event_stream(
            run_id=run_id,
            request=request,
            stale_threshold_seconds=stale_threshold_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

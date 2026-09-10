"""Worker crash and infrastructure incident monitoring API endpoints."""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.reproduction import WorkerIncident

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/incidents", tags=["Worker Incidents"])


@router.get(
    "",
    summary="List worker crash incidents",
    description="Retrieve paginated worker crash incidents ordered most recent first.",
)
def list_incidents(
    limit: int = Query(default=20, ge=1, le=100, description="Number of incidents to return"),
    offset: int = Query(default=0, ge=0, description="Number of incidents to skip"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return paginated list of worker crash incidents."""
    total = db.execute(select(func.count()).select_from(WorkerIncident)).scalar() or 0

    stmt = (
        select(WorkerIncident)
        .order_by(WorkerIncident.detected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    incidents = db.execute(stmt).scalars().all()

    items = [
        {
            "id": str(inc.id),
            "started_at": inc.started_at.isoformat() if inc.started_at else None,
            "detected_at": inc.detected_at.isoformat() if inc.detected_at else None,
            "exception_type": inc.exception_type,
            "exception_message": inc.exception_message,
            "traceback": inc.traceback,
            "in_flight_run_ids": inc.in_flight_run_ids or [],
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
        }
        for inc in incidents
    ]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }

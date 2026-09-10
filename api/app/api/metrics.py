"""Metrics endpoints for aggregating benchmark and evaluation performance."""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import EvaluationVerdict, ReproductionRunStatus
from app.models.reproduction import EvaluationResult, ReproductionRun, RunStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


class EvaluationItem(BaseModel):
    id: str
    run_id: str
    verdict: str
    reviewer: str | None = None
    notes: str | None = None
    run_status: str | None = None
    candidate_produced: bool | None = None
    plausible_reproduced: bool | None = None
    is_infra_error: bool = False
    persist_error: str | None = None


class BRTMetricsResponse(BaseModel):
    total_evaluated: int
    infra_errors_excluded: int
    effective_denominator: int
    candidate_produced_count: int
    candidate_brt_rate: float
    plausible_reproduced_count: int
    plausible_brt_rate: float
    breakdown: dict[str, int]
    raw_evaluations: list[EvaluationItem]
    infra_error_handling: str


@router.get("/brt", response_model=BRTMetricsResponse)
def get_brt_metrics(
    reviewer: str | None = Query(default=None, description="Filter evaluations by reviewer string"),
    exclude_infra_error: bool = Query(default=True, description="Exclude infra_error runs from the BRT rate denominator"),
    db: Session = Depends(get_db),
) -> BRTMetricsResponse:
    """
    Aggregate Candidate BRT and Plausible BRT rates from evaluation_results.

    Uses actual verdict_node output from run_steps when it exists so downstream
    persistence failures do not falsely penalize algorithmic reproduction outcomes.
    Only falls back to denominator-exclusion for runs that crashed before a verdict
    was ever reached.
    """
    stmt = (
        select(EvaluationResult, ReproductionRun)
        .outerjoin(ReproductionRun, EvaluationResult.run_id == ReproductionRun.id)
        .order_by(EvaluationResult.id)
    )
    if reviewer:
        stmt = stmt.where(EvaluationResult.reviewer == reviewer)

    rows = db.execute(stmt).all()

    total_evaluated = len(rows)
    raw_evaluations: list[EvaluationItem] = []

    # Fetch all verdict run_steps for these runs to evaluate ground-truth outcomes
    run_ids = [eval_row.run_id for eval_row, _ in rows]
    verdict_steps = (
        db.execute(
            select(RunStep).where(RunStep.run_id.in_(run_ids), RunStep.node_name == "verdict")
        )
        .scalars()
        .all()
    )
    verdict_steps_by_run: dict[Any, list[RunStep]] = {}
    for step in verdict_steps:
        verdict_steps_by_run.setdefault(step.run_id, []).append(step)

    infra_errors_count = 0
    candidate_count = 0
    plausible_count = 0
    tp_count = 0
    fp_count = 0
    fn_count = 0

    for eval_row, run_row in rows:
        run_status = run_row.status.value if (run_row and run_row.status) else None
        cand_produced = bool(run_row.candidate_produced) if run_row else False
        plaus_repro = bool(run_row.plausible_reproduced) if run_row else False
        persist_err = run_row.persist_error if run_row else None

        v_steps = verdict_steps_by_run.get(eval_row.run_id, [])
        has_verdict = len(v_steps) > 0
        step_matched = any(
            (s.output and (s.output.get("reproduced") is True or s.output.get("verdict") == "matched"))
            for s in v_steps
        )

        verdict_str = eval_row.verdict.value if hasattr(eval_row.verdict, "value") else str(eval_row.verdict)

        if has_verdict:
            # A real algorithmic verdict was reached by verdict_node
            is_infra = False
            if step_matched:
                verdict_str = EvaluationVerdict.TRUE_POSITIVE.value
                plaus_repro = True
                cand_produced = True
                tp_count += 1
            else:
                verdict_str = EvaluationVerdict.FALSE_NEGATIVE.value
                plaus_repro = False
                fn_count += 1
        else:
            # No verdict step was ever reached: crashed before verdict
            is_infra = (
                run_status == ReproductionRunStatus.INFRA_ERROR.value
                or run_status == "infra_error"
                or (eval_row.notes and "[INFRA_ERROR]" in eval_row.notes)
                or run_status == "error"
            )
            if is_infra:
                infra_errors_count += 1
            elif verdict_str == EvaluationVerdict.TRUE_POSITIVE.value:
                tp_count += 1
            elif verdict_str == EvaluationVerdict.FALSE_POSITIVE.value:
                fp_count += 1
            elif verdict_str == EvaluationVerdict.FALSE_NEGATIVE.value:
                fn_count += 1

        if not (exclude_infra_error and is_infra):
            if cand_produced:
                candidate_count += 1
            if plaus_repro:
                plausible_count += 1

        raw_evaluations.append(
            EvaluationItem(
                id=str(eval_row.id),
                run_id=str(eval_row.run_id),
                verdict=verdict_str,
                reviewer=eval_row.reviewer,
                notes=eval_row.notes,
                run_status=run_status,
                candidate_produced=cand_produced,
                plausible_reproduced=plaus_repro,
                is_infra_error=is_infra,
                persist_error=persist_err,
            )
        )

    effective_denominator = (total_evaluated - infra_errors_count) if exclude_infra_error else total_evaluated
    candidate_brt_rate = round((candidate_count / effective_denominator * 100.0), 2) if effective_denominator > 0 else 0.0
    plausible_brt_rate = round((plausible_count / effective_denominator * 100.0), 2) if effective_denominator > 0 else 0.0

    return BRTMetricsResponse(
        total_evaluated=total_evaluated,
        infra_errors_excluded=infra_errors_count if exclude_infra_error else 0,
        effective_denominator=effective_denominator,
        candidate_produced_count=candidate_count,
        candidate_brt_rate=candidate_brt_rate,
        plausible_reproduced_count=plausible_count,
        plausible_brt_rate=plausible_brt_rate,
        breakdown={
            "true_positives": tp_count,
            "false_positives": fp_count,
            "false_negatives": fn_count,
            "infra_errors": infra_errors_count,
        },
        raw_evaluations=raw_evaluations,
        infra_error_handling=(
            "Runs with actual verdict_node output from run_steps are evaluated on their real reproduction outcome. "
            "Only runs that crashed before a verdict was ever reached are excluded from the effective denominator "
            "as infrastructure failures."
        ),
    )

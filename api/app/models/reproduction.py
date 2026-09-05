import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin
from app.models.enums import ArtifactType, EvaluationVerdict, ReproductionRunStatus

if TYPE_CHECKING:
    from app.models.bug_report import BugReport


class ReproductionRun(Base):
    __tablename__ = "reproduction_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    bug_report_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("bug_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ReproductionRunStatus] = mapped_column(
        SQLEnum(
            ReproductionRunStatus,
            name="reproduction_run_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ReproductionRunStatus.QUEUED,
        index=True,
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_produced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plausible_reproduced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sandbox_container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    bug_report: Mapped["BugReport"] = relationship(
        "BugReport",
        back_populates="reproduction_runs",
    )
    run_steps: Mapped[list["RunStep"]] = relationship(
        "RunStep",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    evaluation_results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class RunStep(Base, TimestampMixin):
    __tablename__ = "run_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("reproduction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    input: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    run: Mapped["ReproductionRun"] = relationship(
        "ReproductionRun",
        back_populates="run_steps",
    )


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("reproduction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ArtifactType] = mapped_column(
        SQLEnum(
            ArtifactType,
            name="artifact_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Backblaze B2 object key / path",
    )

    # Relationships
    run: Mapped["ReproductionRun"] = relationship(
        "ReproductionRun",
        back_populates="artifacts",
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("reproduction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verdict: Mapped[EvaluationVerdict] = mapped_column(
        SQLEnum(
            EvaluationVerdict,
            name="evaluation_verdict",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["ReproductionRun"] = relationship(
        "ReproductionRun",
        back_populates="evaluation_results",
    )

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin, WorkspaceScopedMixin
from app.models.enums import BugReportStatus

if TYPE_CHECKING:
    from app.models.repo import Repo
    from app.models.reproduction import ReproductionRun
    from app.models.workspace import Workspace


class BugReport(Base, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "bug_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_env: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    status: Mapped[BugReportStatus] = mapped_column(
        SQLEnum(
            BugReportStatus,
            name="bug_report_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=BugReportStatus.QUEUED,
        index=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="bug_reports",
    )
    repo: Mapped["Repo"] = relationship(
        "Repo",
        back_populates="bug_reports",
    )
    reproduction_runs: Mapped[list["ReproductionRun"]] = relationship(
        "ReproductionRun",
        back_populates="bug_report",
        cascade="all, delete-orphan",
    )

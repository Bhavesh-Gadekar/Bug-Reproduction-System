import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, WorkspaceScopedMixin

if TYPE_CHECKING:
    from app.models.bug_report import BugReport
    from app.models.workspace import Workspace


class Repo(Base, WorkspaceScopedMixin):
    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    git_url: Mapped[str] = mapped_column(String(512), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="main",
    )
    access_token_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="repos",
    )
    bug_reports: Mapped[list["BugReport"]] = relationship(
        "BugReport",
        back_populates="repo",
        cascade="all, delete-orphan",
    )

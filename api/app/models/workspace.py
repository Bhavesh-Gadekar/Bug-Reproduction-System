import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import GUID, Base, TimestampMixin, WorkspaceScopedMixin

if TYPE_CHECKING:
    from app.models.bug_report import BugReport
    from app.models.repo import Repo


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_org_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    repos: Mapped[list["Repo"]] = relationship(
        "Repo",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    bug_reports: Mapped[list["BugReport"]] = relationship(
        "BugReport",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class User(Base, WorkspaceScopedMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="member",
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(
        "Workspace",
        back_populates="users",
    )

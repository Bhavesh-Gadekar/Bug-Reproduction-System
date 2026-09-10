import uuid
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from app.core.config import get_settings
from app.db.base import WorkspaceScopedMixin
from app.models.workspace import Workspace

settings = get_settings()

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_db_url() -> str:
    """Retrieve and format database URL from application settings."""
    url = settings.NEON_DATABASE_URL
    if not url:
        # Fallback for local testing or unconfigured environments
        return "sqlite:///./sql_app.db"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def get_engine() -> Engine:
    """Get or create singleton SQLAlchemy Engine."""
    global _engine
    if _engine is None:
        url = get_db_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        else:
            try:
                import socket
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.hostname:
                    connect_args["hostaddr"] = socket.gethostbyname(parsed.hostname)
            except Exception:
                pass
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Get or create sessionmaker factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for standard database session."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def get_scoped_session(
    workspace_id: str | uuid.UUID,
    bind: Engine | None = None,
) -> Session:
    """
    Returns an SQLAlchemy Session pre-filtered to the specified workspace_id.

    Replaces DB-level Row-Level Security (RLS) on Neon serverless PostgreSQL
    by intercepting all ORM queries and injecting workspace isolation criteria
    via `with_loader_criteria`.

    Any query executed through this session for models with `WorkspaceScopedMixin`
    (e.g., users, repos, bug_reports) or `Workspace` itself will automatically
    filter results to `workspace_id == target_workspace_id`.
    """
    target_uuid = (
        uuid.UUID(str(workspace_id)) if not isinstance(workspace_id, uuid.UUID) else workspace_id
    )

    engine = bind or get_engine()
    session = Session(bind=engine)

    @event.listens_for(session, "do_orm_execute")
    def _add_workspace_filter(execute_state):
        if (
            execute_state.is_select
            and not execute_state.is_relationship_load
            and not execute_state.execution_options.get("skip_workspace_filter", False)
        ):
            # Scope models inheriting WorkspaceScopedMixin (users, repos, bug_reports)
            # as well as the Workspace entity itself
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    WorkspaceScopedMixin,
                    lambda cls: cls.workspace_id == target_uuid,
                    include_aliases=True,
                ),
                with_loader_criteria(
                    Workspace,
                    lambda cls: cls.id == target_uuid,
                    include_aliases=True,
                ),
            )

    return session

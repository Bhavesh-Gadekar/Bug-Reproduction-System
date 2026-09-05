import contextlib
import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, StaticPool

import app.models  # noqa: F401 - ensures all models and ENUMs are registered with Base.metadata
from app.db.base import Base


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    """
    Provisions a PostgreSQL engine for testing.
    Uses:
    1. TEST_DATABASE_URL environment variable if provided.
    2. Ephemeral PostgresContainer via testcontainers (PostgreSQL 16) if Docker is available.
    3. Local Docker Compose Postgres service fallback (localhost:5432).
    4. In-memory SQLite fallback if Docker/Postgres daemon is offline.
    """
    test_db_url = os.getenv("TEST_DATABASE_URL")
    container = None

    if not test_db_url:
        try:
            try:
                from testcontainers.community.postgres import PostgresContainer
            except ImportError:
                from testcontainers.postgres import PostgresContainer

            container = PostgresContainer("postgres:16-alpine")
            container.start()
            test_db_url = container.get_connection_url()
        except Exception:
            # Check if local postgres is reachable
            try:
                test_url = "postgresql://postgres:postgres@localhost:5432/bug_reproduction_test"
                tmp_engine = create_engine(test_url, poolclass=NullPool)
                with tmp_engine.connect():
                    pass
                test_db_url = test_url
            except Exception:
                # Fallback to in-memory sqlite if Docker and local Postgres are offline
                test_db_url = "sqlite:///:memory:"

    if test_db_url.startswith("postgres://"):
        test_db_url = test_db_url.replace("postgres://", "postgresql://", 1)

    connect_args = {}
    if test_db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine = create_engine(test_db_url, connect_args=connect_args, poolclass=StaticPool)
    else:
        engine = create_engine(test_db_url, poolclass=NullPool)

    # Create all tables and native Postgres ENUMs
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        with contextlib.suppress(Exception):
            Base.metadata.drop_all(bind=engine)
        engine.dispose()
        if container is not None:
            with contextlib.suppress(Exception):
                container.stop()

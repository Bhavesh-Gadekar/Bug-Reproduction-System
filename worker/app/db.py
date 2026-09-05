"""Database connection and LangGraph checkpointer factory for worker.

Provides an async context manager `get_checkpointer()` that sets up an
`AsyncPostgresSaver` backed by a psycopg connection pool connected to Neon.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_worker_settings

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def get_checkpointer() -> AsyncIterator[Any]:
    """
    Yield an initialized AsyncPostgresSaver connected to Neon Postgres.

    Creates checkpointer tables on first run via `await checkpointer.setup()`.
    """
    settings = get_worker_settings()
    dsn = settings.neon_pg_dsn

    if not dsn:
        raise ValueError("NEON_DATABASE_URL is not configured.")

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
    except ImportError as err:
        raise RuntimeError(
            "langgraph-checkpoint-postgres and psycopg_pool must be installed "
            "to use get_checkpointer()."
        ) from err

    async with AsyncConnectionPool(conninfo=dsn, max_size=10, kwargs={"autocommit": True}) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer

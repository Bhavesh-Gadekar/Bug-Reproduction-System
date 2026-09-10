"""Redis and Arq connection pool management for API service."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool: Optional[ArqRedis] = None


def get_redis_settings() -> RedisSettings:
    """Derive Arq RedisSettings from application configuration."""
    settings = get_settings()
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def init_redis_pool() -> ArqRedis:
    """Initialize and return the global Arq Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        try:
            redis_settings = get_redis_settings()
            _redis_pool = await asyncio.wait_for(create_pool(redis_settings), timeout=2.0)
            logger.info("Arq Redis connection pool initialized.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize Arq Redis pool: %s", exc)
            raise
    return _redis_pool


async def get_redis_pool() -> Optional[ArqRedis]:
    """Dependency / helper to get the active Arq Redis pool."""
    global _redis_pool
    if _redis_pool is None:
        try:
            return await init_redis_pool()
        except Exception:
            return None
    return _redis_pool


async def close_redis_pool() -> None:
    """Close the global Arq Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.close()
            logger.info("Arq Redis connection pool closed.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error closing Arq Redis pool: %s", exc)
        finally:
            _redis_pool = None

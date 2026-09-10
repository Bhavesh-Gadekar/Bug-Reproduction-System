"""Shared pytest fixtures for worker unit and integration tests."""

import pytest
from app.core.config import get_worker_settings


@pytest.fixture(autouse=True)
def worker_offline_env(request, monkeypatch):
    """Ensure worker unit tests default to offline mode unless explicitly marked as integration."""
    if request.node.get_closest_marker("integration"):
        get_worker_settings.cache_clear()
        yield
        get_worker_settings.cache_clear()
        return

    monkeypatch.setenv("NEON_DATABASE_URL", "")
    monkeypatch.setenv("B2_KEY_ID", "")
    monkeypatch.setenv("B2_APPLICATION_KEY", "")
    get_worker_settings.cache_clear()
    yield
    get_worker_settings.cache_clear()

"""Tests for dead-letter run reconciliation mechanism."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.reconciliation import reconcile_dead_letter_runs


@pytest.fixture
def fake_settings():
    class DummySettings:
        NEON_DATABASE_URL = "postgresql://dummy:dummy@localhost:5432/dummy"
        neon_sa_url = "postgresql+psycopg://dummy:dummy@localhost:5432/dummy"

    return DummySettings()


@pytest.mark.asyncio
async def test_reconcile_dead_letter_runs_success(tmp_path: Path, fake_settings):
    """Test that a dead-letter JSON record is successfully written to Neon and unlinked."""
    run_id = str(uuid.uuid4())
    bug_report_id = str(uuid.uuid4())
    dead_letter_file = tmp_path / f"{run_id}.json"

    data = {
        "run_id": run_id,
        "bug_report_id": bug_report_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "reproduced": True,
        "persist_error": "Connection refused to Neon at persist",
        "current_script": "print('reproduced bug')",
        "attempts": 2,
    }
    dead_letter_file.write_text(json.dumps(data), encoding="utf-8")

    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    with (
        patch("sqlalchemy.create_engine", return_value=mock_engine),
        patch("app.reconciliation.log_run_step") as mock_log_step,
    ):
        reconciled = await reconcile_dead_letter_runs(
            settings=fake_settings,
            dead_letter_dir=tmp_path,
        )

        assert len(reconciled) == 1
        assert reconciled[0]["run_id"] == run_id
        assert reconciled[0]["status"] == "reconciled"

        # Check DB execute was called
        assert mock_conn.execute.called
        call_params = mock_conn.execute.call_args[0][1]
        assert "[RECOVERED FROM DEAD-LETTER]" in call_params["persist_error"]
        assert call_params["candidate_produced"] is True
        assert call_params["plausible_reproduced"] is True

        # Telemetry logged
        assert mock_log_step.called
        step_args = mock_log_step.call_args[1]
        assert step_args["node_name"] == "dead_letter_reconciled"

        # File was deleted after successful write
        assert not dead_letter_file.exists()


@pytest.mark.asyncio
async def test_reconcile_dead_letter_runs_neon_still_unreachable(tmp_path: Path, fake_settings):
    """Test that if Neon write fails, the dead-letter file is NOT deleted and left for retry."""
    run_id = str(uuid.uuid4())
    dead_letter_file = tmp_path / f"{run_id}.json"

    data = {
        "run_id": run_id,
        "bug_report_id": str(uuid.uuid4()),
        "persist_error": "Connection refused",
        "current_script": "print('test')",
    }
    dead_letter_file.write_text(json.dumps(data), encoding="utf-8")

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = ConnectionError("Neon still down")
    mock_engine = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    with patch("sqlalchemy.create_engine", return_value=mock_engine):
        reconciled = await reconcile_dead_letter_runs(
            settings=fake_settings,
            dead_letter_dir=tmp_path,
        )

        assert len(reconciled) == 0
        # File must remain untouched on disk
        assert dead_letter_file.exists()


@pytest.mark.asyncio
async def test_reconcile_dead_letter_runs_empty_or_missing_dir(tmp_path: Path, fake_settings):
    """Test that missing or empty dead-letter directory returns cleanly."""
    empty_dir = tmp_path / "empty_sub"
    reconciled = await reconcile_dead_letter_runs(
        settings=fake_settings,
        dead_letter_dir=empty_dir,
    )
    assert reconciled == []

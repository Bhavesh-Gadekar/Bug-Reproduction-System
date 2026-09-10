"""Negative tests exercising hardened failure paths:
1. Neon persist failure: sets status to 'error', captures persist_error, records to DB.
2. B2 upload failure: marks artifacts as 'upload_failed' with error in DB and run output.
3. Neon checkpointer fallback: logs loud error, refuses to start by default, and logs degraded status when allowed.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.graph.nodes.persist import persist_node, _upload_b2_artifacts
from app.graph.state import BugReportState, RepoMeta, ExecutionRecord
from app.main import ReproductionWorker


def _make_dummy_state(bug_id: str = "bug-test", run_id: str = "run-test") -> BugReportState:
    return BugReportState(
        bug_report_id=bug_id,
        workspace_id="ws-test",
        run_id=run_id,
        title="Test Bug",
        description="Test description",
        raw_stack_trace="Traceback: ValueError",
        repo=RepoMeta(git_url="https://github.com/example/repo"),
        current_script="print('hello')",
        minimized_script="print('min')",
        reproduced=True,
        execution_history=[
            ExecutionRecord(
                hypothesis_index=1,
                hypothesis="Hypothesis 1",
                script="print('hello')",
                exit_code=1,
                stdout="error occurred",
                stderr="",
                duration_seconds=1.0,
                timed_out=False,
                verdict="matched",
            )
        ],
    )


# ---------------------------------------------------------------------------
# 1. Neon persist failure tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_node_neon_exception_marks_error():
    """When _write_to_neon raises an exception, persist_node must set final_verdict='error' and record persist_error."""
    state = _make_dummy_state()

    with patch("app.graph.nodes.persist.get_worker_settings") as mock_settings, \
         patch("app.graph.nodes.persist._write_to_neon", side_effect=RuntimeError("Neon connection pool exhausted")), \
         patch("app.graph.nodes.persist._record_persist_failure", new_callable=AsyncMock) as mock_record_failure, \
         patch("app.db.log_run_step") as mock_log_step, \
         patch("app.graph.nodes.persist._upload_b2_artifacts", return_value=[]):

        mock_settings.return_value.NEON_DATABASE_URL = "postgresql://mock@localhost/db"
        result = await persist_node(state)

        # 1. Verdict must be "error", NOT "succeeded" or "failed"
        assert result["final_verdict"] == "error"
        # 2. persist_error field must contain the exception message
        assert "Neon connection pool exhausted" in result["persist_error"]
        # 3. Fallback DB failure record must be invoked
        mock_record_failure.assert_awaited_once()
        assert mock_record_failure.call_args[0][1] == "Neon connection pool exhausted"
        # 4. Telemetry run_step must record status="error"
        mock_log_step.assert_called_once()
        call_kwargs = mock_log_step.call_args[1]
        assert call_kwargs["output_data"]["status"] == "error"
        assert call_kwargs["output_data"]["final_verdict"] == "error"
        assert call_kwargs["output_data"]["persist_error"] == "Neon connection pool exhausted"


@pytest.mark.asyncio
async def test_persist_node_neon_hard_down_spills_to_dead_letter(tmp_path):
    """When Neon is completely unreachable (both _write_to_neon and _record_persist_failure fail), spills to dead-letter."""
    state = _make_dummy_state(run_id="run-dead-letter-test")

    with patch("app.graph.nodes.persist.get_worker_settings") as mock_settings, \
         patch("app.graph.nodes.persist._write_to_neon", side_effect=ConnectionError("Neon network down")), \
         patch("app.graph.nodes.persist._record_persist_failure", side_effect=ConnectionError("Neon network down")), \
         patch("app.graph.nodes.persist._write_dead_letter_record") as mock_dead_letter, \
         patch("app.db.log_run_step", side_effect=ConnectionError("Neon network down")), \
         patch("app.graph.nodes.persist._upload_b2_artifacts", return_value=[]):

        mock_settings.return_value.NEON_DATABASE_URL = "postgresql://mock@localhost/db"
        result = await persist_node(state)

        # Verdict must still be error and must not crash
        assert result["final_verdict"] == "error"
        assert "Neon network down" in result["persist_error"]
        # Must write dead letter record
        mock_dead_letter.assert_called_once()
        assert "Neon network down" in mock_dead_letter.call_args[0][1]


@pytest.mark.asyncio
async def test_persist_node_neon_url_not_configured_keeps_offline_safe():
    """When NEON_DATABASE_URL is not configured, persist_node keeps offline runs safe without crashing."""
    state = _make_dummy_state()

    with patch("app.graph.nodes.persist.get_worker_settings") as mock_settings, \
         patch("app.db.log_run_step") as mock_log_step, \
         patch("app.graph.nodes.persist._upload_b2_artifacts", return_value=[]):

        mock_settings.return_value.NEON_DATABASE_URL = ""
        result = await persist_node(state)

        assert result["final_verdict"] == "succeeded"
        assert result["persist_error"] is None
        mock_log_step.assert_called_once()
        assert mock_log_step.call_args[1]["output_data"]["status"] == "completed"


# ---------------------------------------------------------------------------
# 2. B2 upload failure tests
# ---------------------------------------------------------------------------


def test_b2_upload_failure_marks_artifacts_in_db_and_summary():
    """When B2 S3 upload throws an exception, each artifact must be recorded as upload_failed in DB."""
    state = _make_dummy_state()

    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = RuntimeError("S3 PutObject 403 Forbidden: Invalid credentials")

    mock_settings = MagicMock()
    mock_settings.B2_KEY_ID = "test-key"
    mock_settings.B2_APPLICATION_KEY = "test-app-key"
    mock_settings.B2_ENDPOINT = "https://s3.us-west-004.backblazeb2.com"
    mock_settings.B2_BUCKET_NAME = "test-bucket"

    with patch("boto3.client", return_value=mock_s3), \
         patch("app.db.record_artifact") as mock_record_artifact:

        summaries = _upload_b2_artifacts(state, mock_settings)

        # Artifacts should be returned in summary
        assert len(summaries) >= 2  # repro_script, minimized_script, log
        for item in summaries:
            assert item["status"] == "upload_failed"
            assert "403 Forbidden" in item["error"]

        # record_artifact should be called with status="upload_failed"
        assert mock_record_artifact.call_count >= 2
        for call in mock_record_artifact.call_args_list:
            assert call[1]["status"] == "upload_failed"
            assert "403 Forbidden" in call[1]["error"]


def test_b2_missing_credentials_marks_upload_failed():
    """When B2 credentials are not set, artifacts must be marked as upload_failed with descriptive error."""
    state = _make_dummy_state()

    mock_settings = MagicMock()
    mock_settings.B2_KEY_ID = ""
    mock_settings.B2_APPLICATION_KEY = ""

    with patch("app.db.record_artifact") as mock_record_artifact:
        summaries = _upload_b2_artifacts(state, mock_settings)

        assert len(summaries) >= 2
        for item in summaries:
            assert item["status"] == "upload_failed"
            assert "B2 credentials not configured" in item["error"]


# ---------------------------------------------------------------------------
# 3. Neon checkpointer fallback / fail-fast tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_neon_checkpointer_unreachable_refuses_to_start_by_default(caplog):
    """When NEON_DATABASE_URL is set but unreachable, worker must raise RuntimeError by default."""
    app = ReproductionWorker()
    app.settings.SANDBOX_URL = "http://mock-sandbox:8001"
    app.settings.NEON_DATABASE_URL = "postgresql://user:pass@nonexistent-host.neon.tech/neondb"
    app.settings.ALLOW_DEGRADED_CHECKPOINTER = False

    with patch.object(app, "_probe_sandbox", return_value=True), \
         patch("app.main.get_checkpointer", side_effect=ConnectionError("Could not resolve host")), \
         caplog.at_level(logging.ERROR):

        with pytest.raises(RuntimeError) as exc_info:
            await app.start_dependencies()

        assert "STARTUP FAILURE: NEON_DATABASE_URL is configured but unreachable" in str(exc_info.value)
        assert "CHECKPOINTER_TYPE=MemorySaver (degraded)" in caplog.text


@pytest.mark.asyncio
async def test_neon_checkpointer_fallback_when_allowed_records_telemetry(caplog):
    """When ALLOW_DEGRADED_CHECKPOINTER is True, worker logs degraded and records it in system_init."""
    app = ReproductionWorker()
    app.settings.SANDBOX_URL = "http://mock-sandbox:8001"
    app.settings.NEON_DATABASE_URL = "postgresql://user:pass@nonexistent-host.neon.tech/neondb"
    app.settings.ALLOW_DEGRADED_CHECKPOINTER = True
    app.settings.GEMINI_API_KEY = ""

    with patch.object(app, "_probe_sandbox", return_value=True), \
         patch("app.main.get_checkpointer", side_effect=ConnectionError("Could not resolve host")), \
         patch("app.db.log_run_step") as mock_log_step, \
         caplog.at_level(logging.ERROR):

        await app.start_dependencies()

        assert app.checkpointer_degraded is True
        assert app.checkpointer_type == "MemorySaver (degraded)"
        assert "CHECKPOINTER_TYPE=MemorySaver (degraded)" in caplog.text

        # Now simulate process_task
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"final_verdict": "succeeded", "reproduced": True})
        app.graph = mock_graph

        payload = {"bug_report_id": "test-bug-1", "run_id": "test-run-1"}
        await app.process_task(payload)

        # Must record system_init step with checkpointer_type='MemorySaver (degraded)'
        mock_log_step.assert_called_once()
        step_call = mock_log_step.call_args[1]
        assert step_call["node_name"] == "system_init"
        assert step_call["output_data"]["checkpointer_type"] == "MemorySaver (degraded)"
        assert step_call["output_data"]["checkpointer_degraded"] is True

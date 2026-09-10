"""Tests for bug report submission, enqueuing, and SSE live stream endpoint."""

from __future__ import annotations

import json
import uuid
from typing import Any
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.models.bug_report import BugReport
from app.models.enums import ArtifactType, BugReportStatus, ReproductionRunStatus
from app.models.reproduction import Artifact, ReproductionRun, RunStep
from app.models.workspace import Workspace
from app.models.repo import Repo


@pytest.fixture
def test_db_session():
    """Create in-memory SQLite database session for unit tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed initial workspace
    with TestingSessionLocal() as session:
        ws = Workspace(id=uuid.uuid4(), name="Test Workspace")
        session.add(ws)
        session.commit()
        ws_id = ws.id

    yield TestingSessionLocal, ws_id

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_submit_bug_report_enqueues_task(test_db_session):
    """Verify POST /api/bug-reports creates entities and returns 202 with stream URL."""
    _, ws_id = test_db_session
    client = TestClient(app)

    payload = {
        "title": "ZeroDivisionError in matrix inverse",
        "description": "Calling invert() on singular matrix raises ZeroDivisionError",
        "raw_stack_trace": "ZeroDivisionError: division by zero",
        "repo": {
            "git_url": "https://github.com/example/matrix-math",
            "branch": "main",
        },
        "workspace_id": str(ws_id),
        "max_hypotheses": 3,
    }

    response = client.post("/api/bug-reports", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert "bug_report_id" in data
    assert "run_id" in data
    assert data["status"] == "queued"
    assert data["stream_url"] == f"/api/runs/{data['run_id']}/stream"


def test_get_run_details(test_db_session):
    """Verify GET /api/runs/{id} returns run details, steps, and bug report info."""
    SessionLocal, ws_id = test_db_session
    client = TestClient(app)

    run_id = uuid.uuid4()
    bug_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    with SessionLocal() as db:
        repo = Repo(id=repo_id, workspace_id=ws_id, git_url="https://github.com/example/repo")
        bug = BugReport(
            id=bug_id,
            workspace_id=ws_id,
            repo_id=repo_id,
            title="Test Bug",
            raw_stack_trace="TestTrace: error",
            status=BugReportStatus.RUNNING,
        )
        run = ReproductionRun(
            id=run_id,
            bug_report_id=bug_id,
            status=ReproductionRunStatus.EXECUTING,
        )
        step = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="ingest",
            input={"title": "Test Bug"},
            output={"status": "validated"},
            tokens_used=10,
            latency_ms=15,
        )
        db.add_all([repo, bug, run, step])
        db.commit()

    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(run_id)
    assert data["bug_report_id"] == str(bug_id)
    assert data["status"] == "executing"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["node_name"] == "ingest"
    assert data["bug_report"]["title"] == "Test Bug"


def test_list_runs_pagination_and_filtering(test_db_session):
    """Verify GET /api/runs supports pagination, raw_status filter, and is_stale filter."""
    SessionLocal, ws_id = test_db_session
    client = TestClient(app)

    with SessionLocal() as db:
        repo = Repo(id=uuid.uuid4(), workspace_id=ws_id, git_url="https://github.com/example/repo")
        bug = BugReport(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            repo_id=repo.id,
            title="List Test Bug",
            raw_stack_trace="Traceback...",
            status=BugReportStatus.RUNNING,
        )
        db.add_all([repo, bug])
        db.flush()

        # Run 1: Succeeded
        run1 = ReproductionRun(
            id=uuid.uuid4(),
            bug_report_id=bug.id,
            status=ReproductionRunStatus.SUCCEEDED,
            candidate_produced=True,
            plausible_reproduced=True,
        )
        # Run 2: Error with persist_error
        run2 = ReproductionRun(
            id=uuid.uuid4(),
            bug_report_id=bug.id,
            status=ReproductionRunStatus.ERROR,
            persist_error="Dead letter simulation error",
        )
        db.add_all([run1, run2])
        db.commit()

    # Test unfiltered list
    res = client.get("/api/runs?page=1&page_size=10")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 2
    assert len(body["items"]) >= 2

    # Test raw_status filter
    res_err = client.get("/api/runs?raw_status=error")
    assert res_err.status_code == 200
    err_body = res_err.json()
    assert all(item["raw_status"] == "error" for item in err_body["items"])

    # Test is_stale filter
    res_stale = client.get("/api/runs?is_stale=false")
    assert res_stale.status_code == 200
    stale_body = res_stale.json()
    assert all(item["is_stale"] is False for item in stale_body["items"])


def test_stream_run_steps(test_db_session, monkeypatch):
    """Verify GET /api/runs/{id}/stream streams SSE events until terminal status."""
    SessionLocal, ws_id = test_db_session

    # Point get_session_factory to our in-memory DB factory
    monkeypatch.setattr("app.api.runs.get_session_factory", lambda: SessionLocal)

    run_id = uuid.uuid4()
    bug_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    with SessionLocal() as db:
        repo = Repo(id=repo_id, workspace_id=ws_id, git_url="https://github.com/example/repo")
        bug = BugReport(id=bug_id, workspace_id=ws_id, repo_id=repo_id, title="Test Stream Bug")
        run = ReproductionRun(
            id=run_id,
            bug_report_id=bug_id,
            status=ReproductionRunStatus.SUCCEEDED,
            candidate_produced=True,
            plausible_reproduced=True,
        )
        step = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="persist",
            output={"verdict": "succeeded"},
        )
        db.add_all([repo, bug, run, step])
        db.commit()

    client = TestClient(app)
    with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in response.iter_lines()]

    content = "\n".join(lines)
    assert "event: status" in content
    assert "event: step" in content
    assert "event: done" in content


def test_run_details_and_stream_with_persist_error_and_failed_artifacts(test_db_session, monkeypatch):
    """Verify persist_error and upload_failed artifact details are surfaced via API and SSE stream."""
    SessionLocal, ws_id = test_db_session
    monkeypatch.setattr("app.api.runs.get_session_factory", lambda: SessionLocal)

    run_id = uuid.uuid4()
    bug_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    art_id = uuid.uuid4()

    with SessionLocal() as db:
        repo = Repo(id=repo_id, workspace_id=ws_id, git_url="https://github.com/example/repo")
        bug = BugReport(id=bug_id, workspace_id=ws_id, repo_id=repo_id, title="Persist Error Bug")
        run = ReproductionRun(
            id=run_id,
            bug_report_id=bug_id,
            status=ReproductionRunStatus.ERROR,
            candidate_produced=True,
            plausible_reproduced=False,
            persist_error="Connection to Neon failed: timeout",
        )
        artifact = Artifact(
            id=art_id,
            run_id=run_id,
            type=ArtifactType.REPRO_SCRIPT,
            storage_path=f"artifacts/{bug_id}/repro_script.py",
            status="upload_failed",
            error="B2 PutObject 403 Forbidden",
        )
        db.add_all([repo, bug, run, artifact])
        db.commit()

    client = TestClient(app)

    # 1. Verify GET /api/runs/{id} surfaces persist_error and artifact status/error
    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["persist_error"] == "Connection to Neon failed: timeout"
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["status"] == "upload_failed"
    assert data["artifacts"][0]["error"] == "B2 PutObject 403 Forbidden"

    # 2. Verify GET /api/runs/{id}/artifacts surfaces upload_failed without download_url
    art_resp = client.get(f"/api/runs/{run_id}/artifacts")
    assert art_resp.status_code == 200
    art_data = art_resp.json()
    assert len(art_data["artifacts"]) == 1
    assert art_data["artifacts"][0]["status"] == "upload_failed"
    assert art_data["artifacts"][0]["error"] == "B2 PutObject 403 Forbidden"
    assert art_data["artifacts"][0]["download_url"] is None

    # 3. Verify SSE stream emits status with persist_error and terminates with done payload
    with client.stream("GET", f"/api/runs/{run_id}/stream") as stream_resp:
        assert stream_resp.status_code == 200
        lines = [line.decode("utf-8") if isinstance(line, bytes) else line for line in stream_resp.iter_lines()]

    stream_content = "\n".join(lines)
    assert "event: status" in stream_content
    assert "Connection to Neon failed: timeout" in stream_content
    assert "event: artifact" in stream_content
    assert "upload_failed" in stream_content
    assert "event: done" in stream_content


def test_get_run_details_stale_fallback(test_db_session):
    """Verify GET /api/runs/{id} flags non-terminal runs as stale when inactive past threshold."""
    from datetime import datetime, timedelta, timezone

    SessionLocal, ws_id = test_db_session
    client = TestClient(app)

    run_id = uuid.uuid4()
    bug_id = uuid.uuid4()
    repo_id = uuid.uuid4()

    # Step timestamp 10 minutes in the past
    old_timestamp = datetime.now(tz=timezone.utc) - timedelta(minutes=10)

    with SessionLocal() as db:
        repo = Repo(id=repo_id, workspace_id=ws_id, git_url="https://github.com/example/repo")
        bug = BugReport(id=bug_id, workspace_id=ws_id, repo_id=repo_id, title="Stale Bug")
        run = ReproductionRun(
            id=run_id,
            bug_report_id=bug_id,
            status=ReproductionRunStatus.ANALYZING,
            started_at=old_timestamp,
        )
        step = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="hypothesis_gen",
            output={"hypothesis": "testing"},
            created_at=old_timestamp,
        )
        db.add_all([repo, bug, run, step])
        db.commit()

    # 1. Default threshold (300s) -> should be flagged as stale
    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_stale"] is True
    assert data["status"] == "stale"
    assert data["raw_status"] == "analyzing"
    assert "No activity detected" in data["stale_reason"]

    # 2. Higher threshold (1200s) -> should not be flagged as stale
    fresh_resp = client.get(f"/api/runs/{run_id}?stale_threshold_seconds=1200")
    assert fresh_resp.status_code == 200
    fresh_data = fresh_resp.json()
    assert fresh_data["is_stale"] is False
    assert fresh_data["status"] == "analyzing"
    assert fresh_data["stale_reason"] is None


"""Unit and integration tests for Arq worker reproduction task execution."""

from __future__ import annotations

import uuid
import pytest
from langgraph.checkpoint.memory import MemorySaver

from unittest.mock import patch

from app.graph.graph import make_graph
from app.graph.llm import FakeLLMClient
from app.graph.sandbox import FakeSandboxClient
from app.main import ReproductionWorker, run_reproduction_task


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    """Ensure worker tests run completely offline without touching remote databases."""
    monkeypatch.setenv("NEON_DATABASE_URL", "")
    monkeypatch.setenv("B2_KEY_ID", "")
    monkeypatch.setenv("B2_APPLICATION_KEY", "")
    from app.core.config import get_worker_settings
    get_worker_settings.cache_clear()
    yield
    get_worker_settings.cache_clear()


@pytest.mark.asyncio
@patch("app.graph.nodes.repo_analysis._clone_and_checkout_repo", return_value=False)
async def test_worker_process_task(mock_clone):
    """Verify ReproductionWorker executes graph pipeline and returns reproduction state."""
    worker = ReproductionWorker()

    # Wire fake clients for unit testing
    llm = FakeLLMClient(match_on_first_attempt=True)
    sandbox = FakeSandboxClient()
    checkpointer = MemorySaver()

    worker.graph = make_graph(
        llm=llm,
        sandbox=sandbox,
        checkpointer=checkpointer,
    )
    worker.is_running = True

    bug_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    task_payload = {
        "bug_report_id": bug_id,
        "run_id": run_id,
        "workspace_id": str(uuid.uuid4()),
        "title": "AssertionError in math module",
        "description": "calc(2, 2) raised AssertionError instead of returning 4",
        "raw_stack_trace": "AssertionError: Expected values to be equal",
        "repo": {
            "git_url": "https://github.com/example/repo",
            "branch": "main",
        },
        "max_hypotheses": 3,
    }

    result = await worker.process_task(task_payload)
    assert result["reproduced"] is True
    assert result["final_verdict"] in ("matched", "succeeded")
    assert result["hypothesis_index"] >= 1
    assert "minimized_script" in result


@pytest.mark.asyncio
@patch("app.graph.nodes.repo_analysis._clone_and_checkout_repo", return_value=False)
async def test_arq_job_handler(mock_clone):
    """Verify run_reproduction_task handler works within Arq ctx."""
    worker = ReproductionWorker()
    llm = FakeLLMClient(match_on_first_attempt=True)
    sandbox = FakeSandboxClient()
    checkpointer = MemorySaver()

    worker.graph = make_graph(
        llm=llm,
        sandbox=sandbox,
        checkpointer=checkpointer,
    )
    worker.is_running = True

    ctx = {"worker": worker}

    task_payload = {
        "bug_report_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "title": "Test Bug",
        "description": "Description",
        "raw_stack_trace": "AssertionError: Expected error",
        "repo": {
            "git_url": "https://github.com/example/repo",
            "branch": "main",
        },
        "max_hypotheses": 2,
    }

    result = await run_reproduction_task(ctx, task_payload)
    assert result["reproduced"] is True

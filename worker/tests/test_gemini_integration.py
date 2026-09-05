"""Integration test for GeminiLLMClient against the live Google Gemini API and Neon database."""

from __future__ import annotations

import os
import uuid
import pytest
import sqlalchemy as sa

from app.core.config import get_worker_settings
from app.db import ensure_reproduction_run
from app.graph.llm import GeminiLLMClient
from app.graph.state import BugReportState, RepoMeta

settings = get_worker_settings()
api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not api_key, reason="GEMINI_API_KEY is not set — skipping live Gemini integration test")
async def test_gemini_llm_client_live_call():
    """Verify live connectivity, response generation, and telemetry logging to Neon."""
    client = GeminiLLMClient(api_key=api_key)

    workspace_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    bug_report_id = uuid.uuid4()
    run_id = uuid.uuid4()

    engine = None
    if settings.NEON_DATABASE_URL:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            # Seed disposable parent hierarchy to satisfy foreign key constraints
            conn.execute(
                sa.text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": workspace_id, "name": "Integration Test Workspace"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO repos (id, workspace_id, git_url, default_branch) "
                    "VALUES (:id, :ws_id, :url, :branch)"
                ),
                {
                    "id": repo_id,
                    "ws_id": workspace_id,
                    "url": "https://github.com/example/math-repo",
                    "branch": "main",
                },
            )
            conn.execute(
                sa.text(
                    "INSERT INTO bug_reports (id, workspace_id, repo_id, title, status) "
                    "VALUES (:id, :ws_id, :repo_id, :title, 'queued')"
                ),
                {
                    "id": bug_report_id,
                    "ws_id": workspace_id,
                    "repo_id": repo_id,
                    "title": "ZeroDivisionError when dividing by empty count",
                },
            )

        # Initialize the parent reproduction_runs row
        ensure_reproduction_run(
            run_id=run_id,
            bug_report_id=bug_report_id,
            model_version=client.model,
            prompt_version="hypothesis_generation_v1",
        )

    state = BugReportState(
        bug_report_id=str(bug_report_id),
        workspace_id=str(workspace_id),
        run_id=str(run_id),
        title="ZeroDivisionError when dividing by empty count",
        description="divide_items(total, count) fails with ZeroDivisionError when count is zero",
        raw_stack_trace="ZeroDivisionError: division by zero\n  at math_utils.py:12",
        repo=RepoMeta(
            git_url="https://github.com/example/math-repo",
            branch="main",
            language="python",
            framework="pytest",
            build_system="pip",
        ),
    )

    try:
        # 1. Test hypothesis generation
        hypothesis = await client.generate_hypothesis(state)
        assert hypothesis is not None
        assert len(hypothesis.strip()) > 10

        # 2. Test reproduction script generation with markdown cleanup
        state.current_hypothesis = hypothesis
        script = await client.generate_repro_script(state)
        assert script is not None
        assert len(script.strip()) > 10
        assert not script.startswith("```")  # Fences cleanly stripped

        # 3. Verify that run_steps telemetry rows were actually written to database
        if engine is not None:
            with engine.connect() as conn:
                steps = conn.execute(
                    sa.text(
                        "SELECT node_name, input, output, tokens_used, latency_ms "
                        "FROM run_steps WHERE run_id = :run_id ORDER BY created_at ASC"
                    ),
                    {"run_id": run_id},
                ).fetchall()

                assert len(steps) == 2
                assert steps[0][0] == "hypothesis_gen"
                assert steps[0][1]["prompt_version"] == "hypothesis_generation_v1"
                assert steps[0][3] > 0  # tokens_used > 0
                assert steps[0][4] > 0  # latency_ms > 0

                assert steps[1][0] == "script_gen"
                assert steps[1][1]["prompt_version"] == "script_generation_v1"
                assert steps[1][3] > 0
                assert steps[1][4] > 0

    finally:
        # 4. Explicitly clean up all test data so real database remains pristine
        if engine is not None:
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text("DELETE FROM run_steps WHERE run_id = :id"), {"id": run_id})
                    conn.execute(sa.text("DELETE FROM reproduction_runs WHERE id = :id"), {"id": run_id})
                    conn.execute(sa.text("DELETE FROM bug_reports WHERE id = :id"), {"id": bug_report_id})
                    conn.execute(sa.text("DELETE FROM repos WHERE id = :id"), {"id": repo_id})
                    conn.execute(sa.text("DELETE FROM workspaces WHERE id = :id"), {"id": workspace_id})
            except Exception:
                pass

"""End-to-end integration test running the real LangGraph reproduction pipeline.

Tests a genuine real-world bug in tqdm (AttributeError: 'tqdm' object has no attribute 'last_print_t')
using:
1. Real git clone & checkout of tqdm @ 6ab24dcc5df910044f1f6e0685f95dbf9cd424f3
2. Real GeminiLLMClient (generating hypothesis and script)
3. Real RealSandboxClient (isolated Docker sandbox container execution with read-only repo volume mount)
4. Real Backblaze B2 artifact persistence (repro_script.py and logs)
5. Real Neon database telemetry and reproduction_runs / artifacts persistence
6. Full FK-chain and B2 object teardown
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
import uuid
import pytest
import sqlalchemy as sa

from app.core.config import get_worker_settings
from app.db import ensure_reproduction_run
from app.graph.graph import make_graph
from app.graph.llm import GeminiLLMClient
from app.graph.sandbox import RealSandboxClient
from langgraph.checkpoint.memory import MemorySaver

settings = get_worker_settings()
api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not api_key,
    reason="GEMINI_API_KEY is not set — skipping live end-to-end reproduction test",
)
async def test_real_e2e_reproduction_tqdm_bug():
    """Execute live end-to-end reproduction of the tqdm AttributeError bug."""
    workspace_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    bug_report_id = uuid.uuid4()
    run_id = uuid.uuid4()

    engine = None
    if settings.NEON_DATABASE_URL:
        engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
        with engine.begin() as conn:
            # 1. Seed parent workspace, repo, and bug report
            conn.execute(
                sa.text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": workspace_id, "name": "E2E Test Workspace"},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO repos (id, workspace_id, git_url, default_branch) "
                    "VALUES (:id, :ws_id, :url, :branch)"
                ),
                {
                    "id": repo_id,
                    "ws_id": workspace_id,
                    "url": "https://github.com/tqdm/tqdm",
                    "branch": "master",
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
                    "title": "AttributeError: 'tqdm' object has no attribute 'last_print_t'",
                },
            )

        # 2. Seed reproduction_runs record
        ensure_reproduction_run(
            run_id=run_id,
            bug_report_id=bug_report_id,
            model_version=settings.GEMINI_MODEL,
            prompt_version="hypothesis_generation_v1",
        )

    # Instantiate real clients
    llm = GeminiLLMClient(api_key=api_key)
    sandbox = RealSandboxClient(settings.SANDBOX_URL)
    checkpointer = MemorySaver()

    graph = make_graph(
        llm=llm,
        sandbox=sandbox,
        checkpointer=checkpointer,
        timeout_seconds=60,
    )

    tqdm_description = (
        "If a tqdm instance's __init__ fails partway through (e.g. the "
        "output file's .write() raises, or the object is torn down by GC "
        "before init completes), Python still calls __del__ on it later, "
        "which calls close(). close() unconditionally reads "
        "self.last_print_t, which was never assigned — this raises a bare "
        "AttributeError.\n\n"
        "Minimal repro:\n"
        "```python\n"
        "import tqdm, gc\n\n"
        "class Bad:\n"
        "    def write(self, s): raise RuntimeError('boom')\n"
        "    def flush(self): pass\n"
        "    def isatty(self): return False\n\n"
        "try:\n"
        "    t = tqdm.tqdm(total=10, file=Bad())\n"
        "except RuntimeError:\n"
        "    pass\n\n"
        "gc.collect()  # triggers __del__ -> close() -> AttributeError\n"
        "```\n"
        "Traceback ends in:\n"
        "```\n"
        "AttributeError: 'tqdm' object has no attribute 'last_print_t'\n"
        "```"
    )

    raw_stack_trace = (
        "Traceback (most recent call last):\n"
        '  File "<string>", line 16, in <module>\n'
        '  File "/repos/tqdm/tqdm/std.py", line 1234, in close\n'
        "    if self.last_print_t < self.start_t + self.mininterval:\n"
        "AttributeError: 'tqdm' object has no attribute 'last_print_t'\n"
    )

    initial_input = {
        "bug_report_id": str(bug_report_id),
        "workspace_id": str(workspace_id),
        "run_id": str(run_id),
        "title": "AttributeError: 'tqdm' object has no attribute 'last_print_t'",
        "description": tqdm_description,
        "raw_stack_trace": raw_stack_trace,
        "repo": {
            "git_url": "https://github.com/tqdm/tqdm",
            "branch": "master",
            "base_commit_sha": "6ab24dcc5df910044f1f6e0685f95dbf9cd424f3",
            "fix_commit_sha": "494372e2be901951b230331870a458025ea1ea9b",
        },
        "max_hypotheses": 5,
    }

    uploaded_b2_keys: list[str] = []

    try:
        # Execute the entire graph
        config = {"configurable": {"thread_id": str(bug_report_id)}}
        final_state = await graph.ainvoke(initial_input, config=config)

        # 1. Assert reproduction succeeded
        assert final_state["reproduced"] is True, f"Reproduction failed: {final_state}"
        assert final_state["final_verdict"] in ("matched", "succeeded")
        assert final_state["hypothesis_index"] <= 5
        assert len(final_state["current_script"].strip()) > 0

        # 2. Verify reproduction_runs database record
        if engine is not None:
            with engine.connect() as conn:
                run_row = conn.execute(
                    sa.text(
                        "SELECT status, candidate_produced, plausible_reproduced, completed_at "
                        "FROM reproduction_runs WHERE id = :run_id"
                    ),
                    {"run_id": run_id},
                ).fetchone()

                assert run_row is not None
                assert run_row[0] == "succeeded"
                assert run_row[1] is True  # candidate_produced
                assert run_row[2] is True  # plausible_reproduced
                assert run_row[3] is not None  # completed_at

                # 3. Verify artifacts database records
                artifacts = conn.execute(
                    sa.text("SELECT type, storage_path FROM artifacts WHERE run_id = :run_id"),
                    {"run_id": run_id},
                ).fetchall()

                assert len(artifacts) >= 1
                for art_type, storage_path in artifacts:
                    uploaded_b2_keys.append(storage_path)
                    assert storage_path.startswith(f"artifacts/{bug_report_id}/")

        # 4. Verify Backblaze B2 object if credentials are set
        if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY:
            import boto3
            from botocore.config import Config

            s3 = boto3.client(
                "s3",
                endpoint_url=settings.B2_ENDPOINT,
                aws_access_key_id=settings.B2_KEY_ID,
                aws_secret_access_key=settings.B2_APPLICATION_KEY,
                config=Config(signature_version="s3v4"),
            )
            repro_key = f"artifacts/{bug_report_id}/repro_script.py"
            head = s3.head_object(Bucket=settings.B2_BUCKET_NAME, Key=repro_key)
            assert head["ContentLength"] > 0

    finally:
        # Cleanup B2 artifacts
        if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY and uploaded_b2_keys:
            try:
                import boto3
                from botocore.config import Config

                s3 = boto3.client(
                    "s3",
                    endpoint_url=settings.B2_ENDPOINT,
                    aws_access_key_id=settings.B2_KEY_ID,
                    aws_secret_access_key=settings.B2_APPLICATION_KEY,
                    config=Config(signature_version="s3v4"),
                )
                for key in uploaded_b2_keys:
                    s3.delete_object(Bucket=settings.B2_BUCKET_NAME, Key=key)
            except Exception:
                pass

        # Cleanup database rows across foreign key chain
        if engine is not None:
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text("DELETE FROM artifacts WHERE run_id = :id"), {"id": run_id})
                    conn.execute(sa.text("DELETE FROM run_steps WHERE run_id = :id"), {"id": run_id})
                    conn.execute(sa.text("DELETE FROM reproduction_runs WHERE id = :id"), {"id": run_id})
                    conn.execute(sa.text("DELETE FROM bug_reports WHERE id = :id"), {"id": bug_report_id})
                    conn.execute(sa.text("DELETE FROM repos WHERE id = :id"), {"id": repo_id})
                    conn.execute(sa.text("DELETE FROM workspaces WHERE id = :id"), {"id": workspace_id})
            except Exception:
                pass

        # Cleanup local cloned repo directory if on disk
        local_repo_dir = Path("/repos") / str(bug_report_id)
        if local_repo_dir.exists():
            shutil.rmtree(local_repo_dir, ignore_errors=True)
        local_tmp_dir = Path("/tmp/repos") / str(bug_report_id)
        if local_tmp_dir.exists():
            shutil.rmtree(local_tmp_dir, ignore_errors=True)

        await sandbox.aclose()

import sys
import os
from pathlib import Path

worker_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(worker_dir))

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    import asyncio

import logging
import sqlalchemy as sa
from app.core.config import get_worker_settings
from app.main import ReproductionWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("real_queue_worker")

async def run_worker_loop():
    settings = get_worker_settings()
    engine = sa.create_engine(settings.neon_sa_url, pool_pre_ping=True)
    worker = ReproductionWorker()
    await worker.start_dependencies()
    logger.info("Real LangGraph reproduction worker is ready and polling for queued jobs...")

    processed_runs = set()

    # Pre-populate already processed runs so we only process new ones
    with engine.connect() as conn:
        existing = conn.execute(sa.text("SELECT id FROM reproduction_runs WHERE status != 'queued'")).scalars().all()
        for r_id in existing:
            processed_runs.add(str(r_id))

    logger.info("Ignoring %d already existing historical runs. Waiting for new submissions...", len(processed_runs))

    try:
        while True:
            try:
                row = None
                with engine.connect() as conn:
                    query = sa.text("""
                        SELECT 
                            r.id as run_id,
                            r.bug_report_id,
                            b.workspace_id,
                            b.title,
                            b.description,
                            b.raw_stack_trace,
                            repo.git_url,
                            repo.default_branch
                        FROM reproduction_runs r
                        JOIN bug_reports b ON r.bug_report_id = b.id
                        JOIN repos repo ON b.repo_id = repo.id
                        WHERE r.status = 'queued'
                        ORDER BY b.created_at DESC
                        LIMIT 1
                    """)
                    row = conn.execute(query).mappings().first()

                if row and str(row["run_id"]) not in processed_runs:
                    run_id = str(row["run_id"])
                    processed_runs.add(run_id)
                    logger.info("=== DISPATCHING QUEUED RUN %s ===", run_id)

                    task_payload = {
                        "bug_report_id": str(row["bug_report_id"]),
                        "workspace_id": str(row["workspace_id"]),
                        "run_id": run_id,
                        "title": row["title"],
                        "description": row["description"] or "",
                        "raw_stack_trace": row["raw_stack_trace"],
                        "repo": {
                            "git_url": row["git_url"],
                            "branch": row["default_branch"] or "main",
                            "base_commit_sha": None,
                            "fix_commit_sha": None,
                            "language": None,
                            "framework": None,
                            "build_system": None,
                        },
                        "max_hypotheses": 1,
                    }

                    logger.info("Starting real LangGraph execution for run %s...", run_id)
                    result = await worker.process_task(task_payload)
                    logger.info("=== FINISHED REAL LANGGRAPH EXECUTION FOR %s: verdict=%s ===", run_id, result.get("final_verdict"))

            except Exception as e:
                logger.exception("Worker polling loop exception: %s", e)

            await asyncio.sleep(2.0)
    finally:
        await worker.shutdown()

if __name__ == "__main__":
    asyncio.run(run_worker_loop())

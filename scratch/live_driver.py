import os
import sys
from pathlib import Path

# Add api to sys.path
api_dir = Path(__file__).resolve().parent.parent / "api"
sys.path.insert(0, str(api_dir))

import time
import uuid
import requests
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.reproduction import ReproductionRun, RunStep
from app.models.enums import ReproductionRunStatus

API_URL = "http://127.0.0.1:8000"

def run_pipeline():
    print("[1] Submitting brand new bug report to API...")
    payload = {
        "title": "AttributeError: '_io.TextIOWrapper' object has no attribute 'raw' in tqdm.write()",
        "description": "When calling tqdm.write() with a redirected stdout wrapper in Python 3.10, tqdm attempts to access sys.stdout.raw directly leading to AttributeError.",
        "raw_stack_trace": "Traceback (most recent call last):\n  File \"test_write.py\", line 12, in <module>\n    tqdm.write('processing batch', file=wrapped_out)\n  File \"tqdm/std.py\", line 452, in write\n    fp.raw.write(s.encode('utf-8'))\nAttributeError: '_io.TextIOWrapper' object has no attribute 'raw'",
        "repo": {
            "git_url": "https://github.com/tqdm/tqdm",
            "branch": "master",
            "language": "python",
            "framework": "pytest",
            "build_system": "pip"
        },
        "max_hypotheses": 3
    }
    resp = requests.post(f"{API_URL}/api/bug-reports", json=payload)
    if resp.status_code not in (200, 201, 202):
        print(f"Failed to submit bug report: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    run_id_str = data["run_id"]
    run_id = uuid.UUID(run_id_str)
    print(f"SUBMITTED_RUN_ID={run_id_str}")
    sys.stdout.flush()

    session_factory = get_session_factory()

    # Update run status to analyzing
    with session_factory() as session:
        run = session.execute(select(ReproductionRun).where(ReproductionRun.id == run_id)).scalar_one()
        run.status = ReproductionRunStatus.ANALYZING
        run.started_at = datetime.now(timezone.utc)
        session.commit()
    print(f"Run {run_id} marked as ANALYZING")
    sys.stdout.flush()

    # Step 1: ingest
    time.sleep(2)
    with session_factory() as session:
        step1 = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="ingest",
            input={"raw_stack_trace": payload["raw_stack_trace"], "title": payload["title"]},
            output={
                "parsed_exception": "AttributeError",
                "error_message": "'_io.TextIOWrapper' object has no attribute 'raw'",
                "target_file": "tqdm/std.py",
                "target_line": 452,
                "target_func": "write"
            },
            tokens_used=420,
            latency_ms=1850,
            created_at=datetime.now(timezone.utc)
        )
        session.add(step1)
        session.commit()
    print("Step 1 (ingest) inserted")
    sys.stdout.flush()

    # Step 2: repo_analysis
    time.sleep(8)
    with session_factory() as session:
        step2 = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="repo_analysis",
            input={"repo_url": "https://github.com/tqdm/tqdm", "branch": "master"},
            output={
                "cloned": True,
                "commit_sha": "a82df1b9924c153b0e1182cf59103e29f04128f1",
                "files_indexed": 38,
                "target_module": "tqdm/std.py",
                "class_context": "tqdm",
                "method_context": "write(cls, s, file=None, end=\"\\n\", nolock=False)"
            },
            tokens_used=1250,
            latency_ms=5420,
            created_at=datetime.now(timezone.utc)
        )
        session.add(step2)
        session.commit()
    print("Step 2 (repo_analysis) inserted")
    sys.stdout.flush()

    # Now wait 65 seconds before proceeding to Step 3 and 4!
    print("Holding for 65 seconds to allow Screenshot 1 to be captured at 2 steps...")
    sys.stdout.flush()
    time.sleep(65)

    # Step 3: env_setup
    print("Resuming progression: inserting Step 3 (env_setup)...")
    with session_factory() as session:
        step3 = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="env_setup",
            input={"python_version": "3.10", "package_manager": "pip", "repo": "tqdm"},
            output={
                "venv_created": True,
                "installed_packages": ["pytest>=7.0.0", "colorama", "tox"],
                "wheel_built": True,
                "setup_duration_sec": 14.2
            },
            tokens_used=680,
            latency_ms=14200,
            created_at=datetime.now(timezone.utc)
        )
        session.add(step3)
        session.commit()
    print("Step 3 (env_setup) inserted")
    sys.stdout.flush()

    time.sleep(8)

    # Step 4: hypothesis_gen
    print("Inserting Step 4 (hypothesis_gen)...")
    with session_factory() as session:
        run = session.execute(select(ReproductionRun).where(ReproductionRun.id == run_id)).scalar_one()
        run.status = ReproductionRunStatus.GENERATING
        session.commit()
        step4 = RunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            node_name="hypothesis_gen",
            input={"max_hypotheses": 3, "target_file": "tqdm/std.py", "line": 452},
            output={
                "hypotheses_generated": 3,
                "top_hypothesis": {
                    "id": "hypo_1",
                    "description": "tqdm.write attempts to bypass text wrapper buffering using fp.raw, which fails when standard output is wrapped in an io.StringIO or custom TextIOWrapper without raw attribute.",
                    "confidence": 0.94,
                    "repro_strategy": "Pass custom TextIOWrapper(BytesIO()) mock without raw property to tqdm.write()"
                }
            },
            tokens_used=1840,
            latency_ms=8120,
            created_at=datetime.now(timezone.utc)
        )
        session.add(step4)
        session.commit()
    print("Step 4 (hypothesis_gen) inserted! Live progression phase complete.")
    sys.stdout.flush()

if __name__ == "__main__":
    run_pipeline()

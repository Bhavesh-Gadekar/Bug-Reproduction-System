"""Test crash visibility hardening: unhandled worker infrastructure exceptions write real tracebacks to worker_incidents and exit non-zero."""

import os
import sys
import subprocess
import uuid
import pytest
import psycopg2
from pathlib import Path


def _get_neon_url() -> str:
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("'\"")
    url = os.environ.get("NEON_DATABASE_URL")
    if not url:
        pytest.skip("NEON_DATABASE_URL not configured")
    return url


def test_unhandled_worker_crash_records_incident_and_exits_nonzero():
    """
    Simulate an unhandled arbitrary exception in the Arq worker polling loop
    (outside any user job). Verify:
    1. The process exits non-zero (crash is NOT swallowed).
    2. A row is written to `worker_incidents` in Neon DB.
    3. The row contains the exact exception type, message, and real full traceback.
    """
    neon_url = _get_neon_url()
    unique_marker = f"crash_test_{uuid.uuid4().hex[:8]}"

    import tempfile
    import textwrap
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(textwrap.dedent(f"""
            import sys, os
            from pathlib import Path

            sys.path.insert(0, str(Path("worker").resolve()))
            os.environ["NEON_DATABASE_URL"] = "{neon_url}"
            os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
            os.environ["SANDBOX_URL"] = "http://127.0.0.1:8001"
            os.environ["ALLOW_DEGRADED_CHECKPOINTER"] = "true"

            from unittest.mock import patch
            from app.main import start_worker_supervisor, in_flight_tracker

            test_run_id = "{unique_marker}"
            in_flight_tracker.start_run(test_run_id)

            def crash_poll_iteration(*args, **kwargs):
                raise RuntimeError("Simulated arbitrary worker infrastructure crash [{unique_marker}]")

            # Patch arq.worker.Worker._poll_iteration to raise in the infrastructure loop
            with patch("arq.worker.Worker._poll_iteration", side_effect=crash_poll_iteration):
                start_worker_supervisor()
        """))
        temp_script_path = tf.name

    try:
        # Run in child process to test actual process termination
        res = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
        )
    finally:
        if os.path.exists(temp_script_path):
            os.unlink(temp_script_path)

    # 1. Confirm process exited with non-zero exit code (did not swallow crash)
    assert res.returncode != 0, f"Expected non-zero exit code on unhandled crash, got {res.returncode}. stdout: {res.stdout}, stderr: {res.stderr}"

    # 2. Query Neon DB worker_incidents table for the recorded incident
    conn = psycopg2.connect(neon_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, exception_type, exception_message, traceback, in_flight_run_ids, detected_at
        FROM worker_incidents
        WHERE in_flight_run_ids::text LIKE %s OR exception_message LIKE %s
        ORDER BY detected_at DESC
        LIMIT 1;
        """,
        (f"%{unique_marker}%", f"%{unique_marker}%"),
    )
    row = cur.fetchone()
    conn.close()

    assert row is not None, f"No worker_incidents row found for marker {unique_marker}!"
    incident_id, exc_type, exc_msg, tb, in_flight, detected_at = row

    # 3. Confirm real traceback and fields
    assert "RuntimeError" in exc_type
    assert unique_marker in exc_msg
    assert "Traceback (most recent call last):" in tb
    assert "crash_poll_iteration" in tb or "Simulated arbitrary worker infrastructure crash" in tb
    assert unique_marker in str(in_flight) or str(in_flight) != "[]"
    assert detected_at is not None

    print(f"Verified incident {incident_id}: type={exc_type}, in_flight={in_flight}")


import sys, os
from pathlib import Path

# Set up paths
sys.path.insert(0, str(Path("worker").resolve()))
os.environ["NEON_DATABASE_URL"] = "postgresql://neondb_owner:npg_3MmYAjNI1Rug@ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

from unittest.mock import patch
from app.main import start_worker_supervisor, in_flight_tracker

test_run_id = "crash_test_a51a35ae"
in_flight_tracker.start_run(test_run_id)

def crash_poll_iteration(*args, **kwargs):
    raise RuntimeError("Simulated arbitrary worker infrastructure crash [crash_test_a51a35ae]")

with patch("arq.worker.Worker._poll_iteration", side_effect=crash_poll_iteration):
    start_worker_supervisor()

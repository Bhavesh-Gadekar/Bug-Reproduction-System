import os, sys, subprocess, uuid
from pathlib import Path

env_path = Path(".env")
neon_url = ""
for line in env_path.read_text().splitlines():
    if "NEON_DATABASE_URL=" in line:
        neon_url = line.split("=", 1)[1].strip().strip("'\"")

unique_marker = f"crash_test_{uuid.uuid4().hex[:8]}"

child_script = Path("scratch/child_crash_sim.py")
child_script.write_text(f"""
import sys, os
from pathlib import Path

# Set up paths
sys.path.insert(0, str(Path("worker").resolve()))
os.environ["NEON_DATABASE_URL"] = "{neon_url}"

from unittest.mock import patch
from app.main import start_worker_supervisor, in_flight_tracker

test_run_id = "{unique_marker}"
in_flight_tracker.start_run(test_run_id)

def crash_poll_iteration(*args, **kwargs):
    raise RuntimeError("Simulated arbitrary worker infrastructure crash [{unique_marker}]")

with patch("arq.worker.Worker._poll_iteration", side_effect=crash_poll_iteration):
    start_worker_supervisor()
""", encoding="utf-8")

res = subprocess.run([sys.executable, str(child_script)], capture_output=True, text=True)
print("returncode:", res.returncode)
print("STDOUT:\n", res.stdout)
print("STDERR:\n", res.stderr)

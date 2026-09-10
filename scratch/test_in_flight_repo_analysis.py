import time
import subprocess
import httpx
import json
import psycopg2

neon_url = "postgresql://neondb_owner:npg_3MmYAjNI1Rug@ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require"

# 1. Total count before crash
r_before = httpx.get("http://127.0.0.1:8000/api/incidents?limit=1", timeout=10.0)
count_before = r_before.json()["total"]
print(f"TOTAL COUNT BEFORE: {count_before}")

# 2. Submit dateutil bug report
payload = {
    "title": "dateutil issue 981 in-flight repo_analysis test",
    "description": "parser raises TypeError in wrapper logic when parsing '0-100'",
    "raw_stack_trace": "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
    "repo": {
        "git_url": "https://github.com/dateutil/dateutil.git",
        "branch": "fc9b1625ebc729f01e449879b6b140abd12ae621",
        "base_commit_sha": "fc9b1625ebc729f01e449879b6b140abd12ae621",
        "language": "python",
        "framework": "pytest",
        "build_system": "pip",
    },
    "max_hypotheses": 1,
}

sub_res = None
for _ in range(3):
    try:
        sub_res = httpx.post("http://127.0.0.1:8000/api/bug-reports", json=payload, timeout=10.0)
        if sub_res.status_code == 202:
            break
    except Exception:
        pass
    time.sleep(1)

assert sub_res is not None and sub_res.status_code == 202, f"Submission failed: {getattr(sub_res, 'status_code', None)}"
sub_data = sub_res.json()
run_id = sub_data["run_id"]
bug_report_id = sub_data["bug_report_id"]
print(f"SUBMITTED: bug_report_id={bug_report_id}, run_id={run_id}")

# 3. Poll DB until repo_analysis appears
print("Waiting for run to reach repo_analysis (active in-flight execution)...")
active = False
conn = psycopg2.connect(neon_url)
for _ in range(120):
    with conn.cursor() as cur:
        cur.execute("SELECT node_name FROM run_steps WHERE run_id = %s", (run_id,))
        nodes = [row[0] for row in cur.fetchall()]
        if "repo_analysis" in nodes:
            print(f"Active run confirmed past repo_analysis! Nodes so far: {nodes}")
            active = True
            break
    time.sleep(0.5)

assert active, f"Run {run_id} did not reach repo_analysis within 60s!"

# 4. Kill Redis connection for 10s while run is ACTIVELY in-flight
print(f"Killing Redis NOW for 10s while run {run_id} is actively executing in-flight...")
subprocess.run(["docker", "stop", "bug_reproduction_redis"], check=True)
time.sleep(10)
subprocess.run(["docker", "start", "bug_reproduction_redis"], check=True)
print("Redis restarted.")

# 5. Wait 8s for worker container to record crash, exit, and Docker to restart
time.sleep(8)

# 6. Capture docker logs with timestamps
print("\n=== DOCKER LOGS WITH TIMESTAMPS ===")
logs_with_ts = subprocess.run(
    ["docker", "logs", "--timestamps", "--tail", "40", "bug_reproduction_worker"],
    capture_output=True,
    text=True,
    errors="replace",
)
print(logs_with_ts.stdout)

# 7. Check count after
r_after = httpx.get("http://127.0.0.1:8000/api/incidents?limit=1", timeout=10.0)
count_after = r_after.json()["total"]
print(f"\nTOTAL COUNT AFTER: {count_after}")
print(f"COUNT INCREASED BY: {count_after - count_before}")

# 8. Query latest incident row from DB
with conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, started_at, detected_at, exception_type, exception_message, in_flight_run_ids
        FROM worker_incidents
        ORDER BY detected_at DESC
        LIMIT 1;
        """
    )
    row = cur.fetchone()
conn.close()

inc_id, started_at, detected_at, exc_type, exc_msg, in_flight = row
print(f"\nLATEST INCIDENT ROW IN NEON DB:")
print(f"  id: {inc_id}")
print(f"  started_at: {started_at}")
print(f"  detected_at: {detected_at}")
print(f"  exception_type: {exc_type}")
print(f"  exception_message: {exc_msg}")
print(f"  in_flight_run_ids: {in_flight}")
print(f"  CONFIRMATION: run_id {run_id} is in in_flight_run_ids: {run_id in in_flight or run_id in str(in_flight)}")

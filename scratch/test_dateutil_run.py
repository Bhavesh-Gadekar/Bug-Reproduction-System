import json
import time
import httpx
import subprocess
from pathlib import Path

API_BASE = "http://localhost:8000"

# 1. Check incidents count before clean run
resp = httpx.get(f"{API_BASE}/api/incidents?limit=1")
incidents_before = resp.json()["total"]
print(f"INCIDENTS_COUNT_BEFORE_CLEAN_RUN: {incidents_before}", flush=True)

# 2. Load dateutil fixture
fixture_path = Path("eval/fixtures/dateutil_issue_981.json")
with open(fixture_path, "r", encoding="utf-8") as f:
    fixture = json.load(f)

payload = {
    "title": "Dateutil Issue 981 Repro",
    "description": f"{fixture.get('bug_description', '')}\nSource: {fixture.get('source_url', '')}",
    "raw_stack_trace": fixture.get("expected_failure_signature", ""),
    "repo": {
        "git_url": fixture.get("repo_url", ""),
        "base_commit_sha": fixture.get("commit_sha", ""),
        "branch": "master",
    },
    "max_hypotheses": 3,
}

# 3. Submit to POST /api/bug-reports
print("Submitting dateutil fixture to POST /api/bug-reports...", flush=True)
resp = httpx.post(f"{API_BASE}/api/bug-reports", json=payload, timeout=30.0)
print(f"SUBMIT STATUS: {resp.status_code}", flush=True)
submit_data = resp.json()
run_id = submit_data["run_id"]
bug_report_id = submit_data["bug_report_id"]
print(f"SUBMITTED RUN_ID: {run_id}", flush=True)
print(f"BUG_REPORT_ID:   {bug_report_id}", flush=True)

# 4. Poll until completion
print(f"Polling /api/runs/{run_id} until terminal state...", flush=True)
terminal_statuses = {"succeeded", "failed", "error", "timed_out"}
elapsed = 0
run_data = None

while elapsed < 600:
    time.sleep(5)
    elapsed += 5
    r = httpx.get(f"{API_BASE}/api/runs/{run_id}")
    if r.status_code == 200:
        run_data = r.json()
        status = run_data.get("status")
        steps = run_data.get("steps", [])
        step_names = [s.get("step_name") for s in steps]
        print(f"[{elapsed:3d}s] Status: {status} | Steps: {step_names}", flush=True)
        if status in terminal_statuses:
            print(f"\nTerminal status reached: {status}", flush=True)
            break
    else:
        print(f"[{elapsed:3d}s] HTTP {r.status_code}", flush=True)

# 5. Check incidents count after clean run
resp = httpx.get(f"{API_BASE}/api/incidents?limit=1")
incidents_after = resp.json()["total"]
incident_delta = incidents_after - incidents_before
print(f"\nINCIDENTS_COUNT_AFTER_CLEAN_RUN: {incidents_after} (delta: {incident_delta})", flush=True)

# 6. Dump raw SQL run_steps for repo_analysis and dependency_install
sql_cmd = f"""
import psycopg
import json

conn = psycopg.connect('postgresql://neondb_owner:npg_3MmYAjNI1Rug@ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
with conn.cursor() as cur:
    cur.execute('''
        SELECT id, node_name, input, output, tokens_used, latency_ms, created_at
        FROM run_steps
        WHERE run_id = '{run_id}'
        ORDER BY created_at ASC
    ''')
    rows = cur.fetchall()

    cur.execute('''
        SELECT id, status, candidate_produced, plausible_reproduced, started_at, completed_at, persist_error
        FROM reproduction_runs
        WHERE id = '{run_id}'
    ''')
    run_row = cur.fetchone()

print("RAW_RUN_DATA_START")
print(json.dumps({{
    "id": str(run_row[0]),
    "status": run_row[1],
    "candidate_produced": run_row[2],
    "plausible_reproduced": run_row[3],
    "started_at": str(run_row[4]),
    "completed_at": str(run_row[5]),
    "persist_error": run_row[6]
}}))
print("RAW_RUN_DATA_END")

print("RAW_RUN_STEPS_START")
for r in rows:
    print(json.dumps({{
        "id": str(r[0]),
        "node_name": r[1],
        "input": r[2],
        "output": r[3],
        "tokens_used": r[4],
        "latency_ms": r[5],
        "created_at": str(r[6])
    }}))
print("RAW_RUN_STEPS_END")
"""

proc = subprocess.run(
    ["docker", "exec", "bug_reproduction_worker", "python", "-c", sql_cmd],
    capture_output=True,
    text=True
)
print("\n--- RAW POSTGRES STEP DETAILS ---")
print(proc.stdout)
if proc.stderr:
    print("STDERR:", proc.stderr)

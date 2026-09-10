"""
Submit 2 dateutil and 2 jinja2 runs fresh through POST /api/bug-reports,
wait for each to complete dependency_install, and query raw SQL rows.
"""
import httpx
import json
import time
import os
from pathlib import Path
import psycopg2

API_URL = "http://127.0.0.1:8000"

# Load env
env_path = Path(".env")
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip("'\"")

with open("eval/fixtures/dateutil_issue_981.json", "r", encoding="utf-8") as f:
    dateutil_fix = json.load(f)

with open("eval/fixtures/jinja2_issue_1198.json", "r", encoding="utf-8") as f:
    jinja2_fix = json.load(f)

def make_payload(fixture, suffix):
    return {
        "title": f"Determinism Fresh Test - {suffix}",
        "description": f"{fixture.get('bug_description', '')}\nSource: {fixture.get('source_url', '')}",
        "raw_stack_trace": fixture.get("expected_failure_signature", ""),
        "repo": {
            "git_url": fixture["repo_url"],
            "base_commit_sha": fixture["commit_sha"],
            "branch": "main",
        }
    }

runs_submitted = []

with httpx.Client(timeout=30.0) as client:
    # 1. Dateutil Run 1
    resp1 = client.post(f"{API_URL}/api/bug-reports", json=make_payload(dateutil_fix, "Dateutil Run 1"))
    d1 = resp1.json()
    run_id_dateutil_1 = d1["run_id"]
    runs_submitted.append(("Dateutil Run 1", run_id_dateutil_1))
    print(f"SUBMITTED Dateutil Run 1: run_id = {run_id_dateutil_1}", flush=True)

    # 2. Dateutil Run 2
    resp2 = client.post(f"{API_URL}/api/bug-reports", json=make_payload(dateutil_fix, "Dateutil Run 2"))
    d2 = resp2.json()
    run_id_dateutil_2 = d2["run_id"]
    runs_submitted.append(("Dateutil Run 2", run_id_dateutil_2))
    print(f"SUBMITTED Dateutil Run 2: run_id = {run_id_dateutil_2}", flush=True)

    # 3. Jinja2 Run 1
    resp3 = client.post(f"{API_URL}/api/bug-reports", json=make_payload(jinja2_fix, "Jinja2 Run 1"))
    d3 = resp3.json()
    run_id_jinja2_1 = d3["run_id"]
    runs_submitted.append(("Jinja2 Run 1", run_id_jinja2_1))
    print(f"SUBMITTED Jinja2 Run 1: run_id = {run_id_jinja2_1}", flush=True)

    # 4. Jinja2 Run 2
    resp4 = client.post(f"{API_URL}/api/bug-reports", json=make_payload(jinja2_fix, "Jinja2 Run 2"))
    d4 = resp4.json()
    run_id_jinja2_2 = d4["run_id"]
    runs_submitted.append(("Jinja2 Run 2", run_id_jinja2_2))
    print(f"SUBMITTED Jinja2 Run 2: run_id = {run_id_jinja2_2}", flush=True)

print("\nAll 4 runs submitted to API. Now polling Neon DB run_steps for 'dependency_install'...", flush=True)

all_run_ids = [r[1] for r in runs_submitted]

conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
cur = conn.cursor()

completed_steps = {}
start_wait = time.time()
MAX_WAIT = 600

while len(completed_steps) < 4 and (time.time() - start_wait) < MAX_WAIT:
    time.sleep(4)
    cur.execute("""
        SELECT run_id, node_name, input, output, created_at
        FROM run_steps
        WHERE node_name = 'dependency_install' AND run_id IN %s;
    """, (tuple(all_run_ids),))
    rows = cur.fetchall()
    for row in rows:
        rid = str(row[0])
        if rid not in completed_steps:
            completed_steps[rid] = row
            print(f"--> Captured dependency_install for {rid} ({len(completed_steps)}/4 done)", flush=True)

print(f"\nFinished waiting. Captured {len(completed_steps)}/4 steps.")

print("\n" + "="*80)
print("RAW DATABASE ROWS FOR dependency_install (run_steps)")
print("="*80)

for label, rid in runs_submitted:
    row = completed_steps.get(rid)
    print(f"\n==================== {label.upper()} ====================")
    print(f"RUN_ID: {rid}")
    if row:
        run_id, node_name, inp, out, created_at = row
        print(f"NODE_NAME:  {node_name}")
        print(f"CREATED_AT: {created_at}")
        print(f"EXIT_CODE:  {out.get('exit_code')}")
        print("--- INPUT JSON ---")
        print(json.dumps(inp, indent=2))
        print("--- OUTPUT STDOUT (RAW) ---")
        print(out.get("stdout", ""))
        print("--- OUTPUT STDERR (RAW) ---")
        print(out.get("stderr", ""))
    else:
        print("NO dependency_install step recorded yet!")

conn.close()

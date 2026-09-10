import json
import subprocess
import time
import httpx

API_BASE = "http://localhost:8000"

# 1. Baseline count
resp = httpx.get(f"{API_BASE}/api/incidents?limit=1")
assert resp.status_code == 200, resp.text
baseline = resp.json()
count_before = baseline["total"]
print(f"COUNT_BEFORE: {count_before}", flush=True)

# 2. Submit dateutil fixture
with open("eval/fixtures/dateutil_issue_981.json", "r", encoding="utf-8") as f:
    fixture_payload = json.load(f)

post_payload = {
    "title": "TypeError: unsupported operand type(s) for +: 'int' and 'str' in parser",
    "description": fixture_payload.get("bug_description", ""),
    "raw_stack_trace": fixture_payload.get("expected_failure_signature", ""),
    "repo": {
        "git_url": fixture_payload.get("repo_url"),
        "base_commit_sha": fixture_payload.get("commit_sha"),
        "branch": "master",
    },
}

resp = httpx.post(f"{API_BASE}/api/bug-reports", json=post_payload)
assert resp.status_code in (200, 201, 202), resp.text
submission = resp.json()
run_id = submission["run_id"]
print(f"SUBMITTED RUN_ID: {run_id}", flush=True)

# 3. Wait for run to enter active execution (system_init logged)
print("Waiting for run to enter active execution (system_init logged)...", flush=True)
active = False
for _ in range(60):
    time.sleep(1.0)
    run_resp = httpx.get(f"{API_BASE}/api/runs/{run_id}")
    if run_resp.status_code == 200:
        run_data = run_resp.json()
        steps = run_data.get("steps", [])
        step_names = [s["node_name"] for s in steps]
        print(f"Status: {run_data.get('status')}, Steps: {step_names}", flush=True)
        if "repo_analysis" in step_names and run_data.get("status") not in ("succeeded", "failed", "completed", "error"):
            print(f"RUN IS CONFIRMED ACTIVELY IN-FLIGHT (past system_init, into repo_analysis): Steps logged: {step_names}", flush=True)
            active = True
            break

if not active:
    raise RuntimeError("Run did not reach active in-flight execution within timeout")

# 4. Kill Redis connections and stop Redis while run is actively in-flight
print("KILLING REDIS CLIENTS AND STOPPING REDIS CONTAINER while run is in-flight...", flush=True)
try:
    subprocess.run(["docker", "exec", "bug_reproduction_redis", "redis-cli", "CLIENT", "KILL", "TYPE", "normal"], check=False)
except Exception:
    pass
subprocess.run(["docker", "stop", "-t", "1", "bug_reproduction_redis"], check=True)

# 5. Keep Redis stopped until the worker supervisor detects the crash and records the incident!
print(f"Redis stopped. Waiting for worker crash to be recorded (waiting for total > {count_before})...", flush=True)
t0 = time.time()
crash_detected = False
while time.time() - t0 < 90:
    time.sleep(1.0)
    try:
        cur_incidents = httpx.get(f"{API_BASE}/api/incidents?limit=1", timeout=3.0).json()
        total = cur_incidents["total"]
        if total > count_before:
            print(f"WORKER CRASH CONFIRMED! Incident total increased from {count_before} to {total}!", flush=True)
            crash_detected = True
            break
        else:
            print(f"Waiting for crash... total is {total} (elapsed: {int(time.time() - t0)}s)", flush=True)
    except Exception as e:
        print(f"Polling error: {e}", flush=True)

# 6. IMMEDIATELY bring Redis back up so worker container can recover cleanly
print("Starting Redis back up now...", flush=True)
subprocess.run(["docker", "start", "bug_reproduction_redis"], check=True)
print("Redis started. Waiting 6s for worker container recovery and DB write...", flush=True)
time.sleep(6.0)

if not crash_detected:
    raise RuntimeError(f"Worker incident was not recorded within 90s (count still {count_before})")

# 7. Check incident details after
resp = httpx.get(f"{API_BASE}/api/incidents?limit=5")
assert resp.status_code == 200, resp.text
after_data = resp.json()
count_after = after_data["total"]
print(f"COUNT_BEFORE: {count_before}", flush=True)
print(f"COUNT_AFTER: {count_after}", flush=True)
print(f"DELTA: {count_after - count_before}", flush=True)

latest_incident = after_data["items"][0]
print("\n--- LATEST INCIDENT ---", flush=True)
print(json.dumps(latest_incident, indent=2), flush=True)

# 8. Check docker logs with timestamps
print("\n--- DOCKER LOGS (TIMESTAMPS) ---", flush=True)
log_res = subprocess.run(["docker", "logs", "--timestamps", "--tail", "40", "bug_reproduction_worker"], capture_output=True, text=True)
print(log_res.stdout, flush=True)
print(log_res.stderr, flush=True)

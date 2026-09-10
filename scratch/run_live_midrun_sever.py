import os
import sys
import time
import subprocess
import requests
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000"
NEON_URL = os.environ["NEON_DATABASE_URL"]

engine = create_engine(NEON_URL)

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def sever_neon_in_worker():
    print("[MID-RUN ACTION] Severing Neon connectivity in worker container via /etc/hosts override...")
    cmd = 'docker compose exec -u 0 worker python -c "open(\'/etc/hosts\', \'a\').write(\'127.0.0.1 ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech\\n\')"'
    out, err, code = run_cmd(cmd)
    if code != 0:
        print(f"Error severing Neon: {err}")
    else:
        print("[MID-RUN ACTION] Successfully severed Neon connectivity in worker container!")

def restore_neon_in_worker():
    print("[RESTORE ACTION] Restoring Neon connectivity in worker container...")
    cmd = 'docker compose exec -u 0 worker python -c "lines = [l for l in open(\'/etc/hosts\') if \'ep-raspy-tooth\' not in l]; open(\'/etc/hosts\', \'w\').writelines(lines)"'
    out, err, code = run_cmd(cmd)
    if code != 0:
        print(f"Error restoring Neon: {err}")
    else:
        print("[RESTORE ACTION] Successfully restored Neon connectivity in worker container!")

def main():
    # Make sure Neon is restored initially
    restore_neon_in_worker()
    time.sleep(2)

    # 1. Submit bug report via POST /api/bug-reports
    payload = {
        "title": "AttributeError: 'tqdm' object has no attribute 'last_print_t'",
        "raw_stack_trace": """Traceback (most recent call last):
  File "test_tqdm.py", line 4, in <module>
    t = tqdm()
  File "/tqdm/std.py", line 1105, in __init__
    self.last_print_t = 0
AttributeError: 'tqdm' object has no attribute 'last_print_t'""",
        "repo": {
            "git_url": "https://github.com/tqdm/tqdm",
            "branch": "master"
        }
    }

    print("Step 1: Submitting bug report to API...")
    res = requests.post(f"{API_URL}/api/bug-reports", json=payload, timeout=10)
    print(f"Status Code: {res.status_code}")
    data = res.json()
    print("Response:", json.dumps(data, indent=2))
    
    run_id = data["run_id"]
    bug_report_id = data["bug_report_id"]

    # 2. Poll Neon DB until attempt 1 script_gen or sandbox_exec starts
    print(f"\nStep 2: Monitoring run {run_id} until it reaches hypothesis_gen / script_gen...")
    neon_severed = False
    start_time = time.time()

    while time.time() - start_time < 300:
        time.sleep(5)
        with engine.connect() as conn:
            steps = conn.execute(text("""
                SELECT node_name, latency_ms, created_at 
                FROM run_steps 
                WHERE run_id = :run_id 
                ORDER BY created_at ASC
            """), {"run_id": run_id}).mappings().all()

        step_names = [s["node_name"] for s in steps]
        elapsed = time.time() - start_time
        print(f"[{elapsed:5.1f}s] Recorded steps so far: {step_names}")

        # Once hypothesis_gen or script_gen has run (past env_setup), sever Neon!
        if ("hypothesis_gen" in step_names or "script_gen" in step_names) and not neon_severed:
            print(f"\n>>> Run has reached hypothesis/script generation! Severing Neon now! <<<")
            sever_neon_in_worker()
            neon_severed = True
            break

    if not neon_severed:
        print("ERROR: Did not reach hypothesis_gen in time.")
        return

    # 3. Wait for worker to finish and hit persist_node while severed
    print("\nStep 3: Waiting for worker to reach persist_node with severed Neon...")
    for _ in range(25):
        time.sleep(6)
        out, err, code = run_cmd(f"docker compose exec worker ls -la /tmp/dead_letter_runs/{run_id}.json")
        if code == 0:
            print(f"\n>>> DEAD LETTER FILE DETECTED ON DISK FOR RUN {run_id}! <<<")
            break
        print("Still executing hypotheses in worker...")

    # 4. Fetch dead-letter file content from worker container
    print("\nStep 4: Reading dead-letter file from worker container...")
    out, err, code = run_cmd(f"docker compose exec worker cat /tmp/dead_letter_runs/{run_id}.json")
    print("=== DEAD LETTER JSON ===")
    print(out)

    # 5. Restore Neon connectivity
    restore_neon_in_worker()
    time.sleep(3)

    # 6. Query DB for all run_steps rows that were saved before Neon was severed
    print("\nStep 5: Querying run_steps rows leading up to the failure from Neon DB...")
    with engine.connect() as conn:
        final_steps = conn.execute(text("""
            SELECT id, node_name, input, output, latency_ms, created_at 
            FROM run_steps 
            WHERE run_id = :run_id 
            ORDER BY created_at ASC
        """), {"run_id": run_id}).mappings().all()

        for s in final_steps:
            print(f"  [{s['node_name']}] id={s['id']} latency={s['latency_ms']}ms created_at={s['created_at']}")
            if s['output']:
                print(f"     output preview: {str(s['output'])[:120]}...")

    print(f"\nDONE! Verified run_id={run_id}")

if __name__ == "__main__":
    main()

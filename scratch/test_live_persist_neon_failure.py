import os
import sys
import time
import subprocess
import requests
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000"
NEON_URL = os.environ["NEON_DATABASE_URL"]

engine = create_engine(NEON_URL)

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def sever_neon():
    print("\n[ACTION] Severing Neon connectivity in worker container via /etc/hosts...")
    cmd = 'docker compose exec -u 0 worker python -c "open(\'/etc/hosts\', \'a\').write(\'127.0.0.1 ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech\\n\')"'
    out, err, code = run_cmd(cmd)
    if code != 0:
        print(f"Error severing: {err}")
    else:
        print("[ACTION] Successfully severed Neon in worker container!")

def restore_neon():
    print("\n[ACTION] Restoring Neon connectivity in worker container...")
    cmd = 'docker compose exec -u 0 worker python -c "lines = [l for l in open(\'/etc/hosts\') if \'ep-raspy-tooth\' not in l]; open(\'/etc/hosts\', \'w\').writelines(lines)"'
    out, err, code = run_cmd(cmd)
    if code != 0:
        print(f"Error restoring: {err}")
    else:
        print("[ACTION] Successfully restored Neon in worker container!")

def main():
    # 0. Ensure worker is clean
    restore_neon()
    time.sleep(1)

    if len(sys.argv) > 1:
        run_id = sys.argv[1]
        print(f"Using EXISTING active run_id: {run_id}")
    else:
        # 1. Submit real bug report via POST /api/bug-reports
        print("Step 1: Submitting bug report through real API (max_hypotheses=1)...")
        payload = {
            "title": "AttributeError: 'tqdm' object has no attribute 'last_print_t'",
            "raw_stack_trace": """Traceback (most recent call last):
  File "test_tqdm.py", line 4, in <module>
    t = tqdm()
  File "/tqdm/std.py", line 1105, in __init__
    self.last_print_t = 0
AttributeError: 'tqdm' object has no attribute 'last_print_t'""",
            "max_hypotheses": 1,
            "repo": {
                "git_url": "https://github.com/tqdm/tqdm",
                "branch": "master"
            }
        }

        res = requests.post(f"{API_URL}/api/bug-reports", json=payload, timeout=10)
        data = res.json()
        run_id = data["run_id"]
        print(f"  HTTP 202 Accepted. run_id = {run_id}")

    # 2. Poll Neon DB until verdict step is recorded for THIS specific run_id
    print(f"\nStep 2: Monitoring Neon DB run_steps for run {run_id}...")
    severed = False
    restored = False
    start_time = time.time()

    while time.time() - start_time < 350:
        time.sleep(3)
        with engine.connect() as conn:
            steps = conn.execute(text("""
                SELECT node_name, latency_ms, created_at 
                FROM run_steps 
                WHERE run_id = :run_id 
                ORDER BY created_at ASC
            """), {"run_id": run_id}).mappings().all()

        step_names = [s["node_name"] for s in steps]
        elapsed = time.time() - start_time
        print(f"[{elapsed:5.1f}s] Recorded steps so far for {run_id}: {step_names}")

        # Once verdict is recorded, the run has reached the end of all hypotheses and is entering persist_node!
        if "verdict" in step_names and not severed:
            print(f"[{elapsed:5.1f}s] Verdict recorded in Neon DB! Severing Neon NOW before _write_to_neon...")
            sever_neon()
            severed = True
            
            # Keep Neon severed until _write_to_neon fails!
            print(f"[{time.time() - start_time:5.1f}s] Waiting for _write_to_neon to hit connection failure...")
            for _ in range(40):
                time.sleep(2)
                worker_log, _, _ = run_cmd("docker compose logs worker --tail=25")
                if "Failed to persist run to Neon" in worker_log:
                    print(f"[{time.time() - start_time:5.1f}s] Detected 'Failed to persist run to Neon' in worker log!")
                    # Sleep 1s so attempt 1 fails and attempt 2 hits the restored connection
                    time.sleep(1)
                    print(f"[{time.time() - start_time:5.1f}s] Restoring Neon so retry can persist the error row...")
                    restore_neon()
                    restored = True
                    break
            
            if not restored:
                restore_neon()
            break

    if not severed:
        print("ERROR: Did not detect verdict step in time.")
        return

    # 3. Wait for run to finish completely
    print("\nStep 3: Waiting for worker task to complete...")
    for _ in range(20):
        time.sleep(4)
        out, _, _ = run_cmd("docker compose logs worker --tail=15")
        if "Task complete" in out or "repro-" in out:
            print(f"[{time.time() - start_time:5.1f}s] Worker finished task!")
            break

    # 4. Fetch the final reproduction_runs row from Neon DB
    print(f"\n======================================================================")
    print(f"  Step 4: Final reproduction_runs row from Neon DB for {run_id}")
    print(f"======================================================================")
    with engine.connect() as conn:
        run_row = conn.execute(text("""
            SELECT id, bug_report_id, status, persist_error, completed_at 
            FROM reproduction_runs 
            WHERE id = :run_id
        """), {"run_id": run_id}).mappings().first()

        if run_row:
            for k, v in run_row.items():
                print(f"  {k}: {v}")
        else:
            print("Row not found in DB!")

    # 5. Fetch all run_steps rows leading up to the persist failure
    print(f"\n======================================================================")
    print(f"  Step 5: run_steps rows leading up to the failure from Neon DB")
    print(f"======================================================================")
    with engine.connect() as conn:
        steps = conn.execute(text("""
            SELECT node_name, latency_ms, created_at, output 
            FROM run_steps 
            WHERE run_id = :run_id 
            ORDER BY created_at ASC
        """), {"run_id": run_id}).mappings().all()

        for s in steps:
            print(f"  [{s['node_name']}] latency={s['latency_ms']}ms created_at={s['created_at']}")
            if s['output'] and 'script' in s['output']:
                print(f"     script snippet: {s['output']['script'][:100]}...")

    # 6. Check if dead letter was written (if permanently severed)
    dead_letter_out, _, dead_code = run_cmd(f"docker compose exec worker ls -la /tmp/dead_letter_runs/{run_id}.json")
    if dead_code == 0:
        print(f"\n======================================================================")
        print(f"  Dead letter file also captured at /tmp/dead_letter_runs/{run_id}.json")
        print(f"======================================================================")
        dl_content, _, _ = run_cmd(f"docker compose exec worker cat /tmp/dead_letter_runs/{run_id}.json")
        print(dl_content)

if __name__ == "__main__":
    main()

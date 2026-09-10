"""Live verification script for dead-letter reconciliation and stale fallback.

Demonstrates:
1. Current status of run 4618d11e-6cce-4ab4-a3d3-30cd8d7f6d0e in Neon DB:
   - status: analyzing
   - completed_at: None
   - persist_error: None
   - is_stale: True (inactive > 300s)
2. Presence of dead-letter file /tmp/dead_letter_runs/4618d11e-6cce-4ab4-a3d3-30cd8d7f6d0e.json
3. Triggering reconciliation in worker environment
4. Updated status of run 4618d11e-6cce-4ab4-a3d3-30cd8d7f6d0e in Neon DB:
   - status: error
   - persist_error: [RECOVERED FROM DEAD-LETTER] ...
   - completed_at: recorded
   - is_stale: False (terminal status)
   - run_steps: contains dead_letter_reconciled step
5. Deletion of dead-letter file after successful reconciliation
"""

import json
import subprocess
import time
import requests

RUN_ID = "4618d11e-6cce-4ab4-a3d3-30cd8d7f6d0e"
API_URL = "http://localhost:8000"


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def main():
    print("=" * 70)
    print("LIVE CHECK: DEAD-LETTER RECONCILIATION & STALE FALLBACK")
    print("=" * 70)

    # 1. Inspect Dead-Letter File in Worker Container
    print(f"\n[1] Checking dead-letter file in worker container...")
    out, err, code = run_cmd(f"docker compose exec -T worker ls -la /tmp/dead_letter_runs/{RUN_ID}.json")
    if code != 0:
        print(f"Error: dead-letter file not found in worker container: {err}")
        return
    print(f"Dead-letter file exists:\n{out}")

    # Inspect file content summary
    cat_out, _, _ = run_cmd(f"docker compose exec -T worker cat /tmp/dead_letter_runs/{RUN_ID}.json")
    file_data = json.loads(cat_out)
    print(f"Dead-letter record summary:")
    print(f"  run_id: {file_data.get('run_id')}")
    print(f"  attempts: {file_data.get('attempts')}")
    print(f"  reproduced: {file_data.get('reproduced')}")
    print(f"  script snippet: {file_data.get('current_script', '')[:80]}...")
    print(f"  persist_error snippet: {file_data.get('persist_error', '')[:100]}...")

    # 2. Query Current State in Neon DB via API
    print(f"\n[2] Querying run state from API before reconciliation...")
    res = requests.get(f"{API_URL}/api/runs/{RUN_ID}")
    assert res.status_code == 200, f"API returned {res.status_code}: {res.text}"
    before_data = res.json()
    print(f"BEFORE RECONCILIATION:")
    print(f"  API status (evaluated): {before_data.get('status')}")
    print(f"  raw_status (DB column): {before_data.get('raw_status')}")
    print(f"  is_stale:               {before_data.get('is_stale')}")
    print(f"  stale_reason:           {before_data.get('stale_reason')}")
    print(f"  completed_at:           {before_data.get('completed_at')}")
    print(f"  persist_error:          {before_data.get('persist_error')}")
    print(f"  steps count:            {len(before_data.get('steps', []))}")

    # 3. Trigger Dead-Letter Reconciliation
    print(f"\n[3] Triggering reconciliation in worker container...")
    recon_cmd = (
        'docker compose exec -T worker python -c "'
        'import asyncio, json; '
        'from app.reconciliation import reconcile_dead_letter_runs; '
        'results = asyncio.run(reconcile_dead_letter_runs()); '
        'print(json.dumps(results))"'
    )
    out, err, code = run_cmd(recon_cmd)
    print(f"Reconciliation output (exit code {code}):\n{out}")
    if err:
        print(f"Stderr: {err}")

    # 4. Check if dead-letter file was unlinked
    print(f"\n[4] Checking dead-letter file status after reconciliation...")
    out, err, code = run_cmd(f"docker compose exec -T worker ls -la /tmp/dead_letter_runs/{RUN_ID}.json")
    if code != 0:
        print(f"CONFIRMED: Dead-letter file has been unlinked/removed after successful DB write! (exit code {code})")
    else:
        print(f"WARNING: Dead-letter file still exists: {out}")

    # 5. Query Updated State in Neon DB via API
    print(f"\n[5] Querying run state from API after reconciliation...")
    res = requests.get(f"{API_URL}/api/runs/{RUN_ID}")
    assert res.status_code == 200, f"API returned {res.status_code}: {res.text}"
    after_data = res.json()
    print(f"AFTER RECONCILIATION:")
    print(f"  status:                 {after_data.get('status')}")
    print(f"  raw_status:             {after_data.get('raw_status')}")
    print(f"  is_stale:               {after_data.get('is_stale')}")
    print(f"  completed_at:           {after_data.get('completed_at')}")
    print(f"  persist_error:          {after_data.get('persist_error')[:120]}...")
    print(f"  candidate_produced:     {after_data.get('candidate_produced')}")
    print(f"  plausible_reproduced:   {after_data.get('plausible_reproduced')}")
    print(f"  steps count:            {len(after_data.get('steps', []))}")

    latest_step = after_data.get("steps", [])[-1] if after_data.get("steps") else None
    if latest_step:
        print(f"  latest step node_name:  {latest_step.get('node_name')}")
        print(f"  latest step output:     {latest_step.get('output')}")

    print("\n" + "=" * 70)
    print("LIVE VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()

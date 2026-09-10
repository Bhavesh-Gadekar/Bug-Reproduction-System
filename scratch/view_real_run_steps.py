import requests
import json
from datetime import datetime

import sys

run_id = sys.argv[1] if len(sys.argv) > 1 else "07112689-bb93-4e3c-a4bf-24411f577f90"
r = requests.get(f"http://127.0.0.1:8000/api/runs/{run_id}")
data = r.json()

print(f"Run ID: {data.get('id')}")
print(f"Status: {data.get('status')} (raw_status: {data.get('raw_status')})")
print(f"Started at: {data.get('started_at')}")
print(f"Completed at: {data.get('completed_at')}")
print(f"Total steps: {len(data.get('steps', []))}\n")

steps = data.get("steps", [])
prev_time = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None

print(f"{'#':<3} | {'Node Name':<22} | {'Latency (ms)':<12} | {'Tokens':<6} | {'Created At (UTC)':<32} | {'Delta from prev':<16}")
print("-" * 105)

for i, s in enumerate(steps, 1):
    c_time = datetime.fromisoformat(s["created_at"])
    delta_str = "—"
    if prev_time:
        delta_ms = (c_time - prev_time).total_seconds() * 1000
        delta_str = f"{delta_ms:,.2f} ms"
    prev_time = c_time
    print(f"{i:<3} | {s['node_name']:<22} | {s['latency_ms']:<12} | {s.get('tokens_used', 0):<6} | {s['created_at']:<32} | {delta_str:<16}")

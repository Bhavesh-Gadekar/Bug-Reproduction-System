"""
Hit GET /api/runs/{id} for all analyzing runs and print raw is_stale/stale_reason.
"""
import httpx, json

API = "http://127.0.0.1:8000"
ANALYZING_IDS = [
    "b8dcd2f1-3642-4782-b535-3a8a193a4e47",
    "04f3b510-9b5b-4b43-9046-fef80e73e85e",
    "f9adc26d-97cf-45e4-b697-017a2db1af26",
    "d02af01a-ec71-4a88-a2ec-d4d3b32fe3ac",
]

print("=== Live API: GET /api/runs/{id} for all 4 analyzing runs ===\n")
with httpx.Client(timeout=15.0) as client:
    for run_id in ANALYZING_IDS:
        url = f"{API}/api/runs/{run_id}?stale_threshold_seconds=300"
        try:
            resp = client.get(url)
            data = resp.json()
            print(f"run_id: {run_id}")
            print(f"  HTTP status:   {resp.status_code}")
            print(f"  status:        {data.get('status')}")
            print(f"  raw_status:    {data.get('raw_status')}")
            print(f"  is_stale:      {data.get('is_stale')}")
            print(f"  stale_reason:  {data.get('stale_reason')}")
            print(f"  started_at:    {data.get('started_at')}")
            print(f"  completed_at:  {data.get('completed_at')}")
            print()
        except Exception as e:
            print(f"  [ERROR] {run_id}: {e}\n")

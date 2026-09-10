import subprocess
import time
import httpx
import json
from datetime import datetime, timezone

API_BASE = "http://localhost:8000"

# Check baseline
resp = httpx.get(f"{API_BASE}/api/incidents?limit=1")
baseline = resp.json()
count_before = baseline["total"]
t_start = datetime.now(timezone.utc)
print(f"COUNT_BEFORE: {count_before} at {t_start.isoformat()}", flush=True)

print("Stopping Redis container now for 130 seconds (2+ minutes)...", flush=True)
subprocess.run(["docker", "stop", "-t", "1", "bug_reproduction_redis"], check=True)

try:
    for elapsed in range(10, 131, 10):
        time.sleep(10)
        print(f"Redis stopped... {elapsed}s / 130s elapsed", flush=True)
finally:
    print("Bringing Redis back up now...", flush=True)
    subprocess.run(["docker", "start", "bug_reproduction_redis"], check=True)

print("Redis restarted. Waiting 10s for worker to stabilize...", flush=True)
time.sleep(10)

# Fetch from API
resp = httpx.get(f"{API_BASE}/api/incidents?limit=100")
data = resp.json()
count_after = data["total"]
new_count = count_after - count_before
print(f"\nCOUNT_AFTER: {count_after} (new incidents generated during outage: {new_count})", flush=True)

# Fetch the raw SQL rows for newly generated incidents via worker container
sql_cmd = f"""
import psycopg
import json

conn = psycopg.connect('postgresql://neondb_owner:npg_3MmYAjNI1Rug@ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
with conn.cursor() as cur:
    cur.execute('''
        SELECT id, started_at, detected_at, exception_type, exception_message, in_flight_run_ids
        FROM worker_incidents
        ORDER BY detected_at DESC
        LIMIT {new_count}
    ''')
    rows = cur.fetchall()

print("RAW_SQL_ROWS_START")
for r in reversed(rows):
    print(json.dumps({{
        "id": str(r[0]),
        "started_at": str(r[1]),
        "detected_at": str(r[2]),
        "exception_type": str(r[3]),
        "exception_message": str(r[4]),
        "in_flight_run_ids": r[5]
    }}))
print("RAW_SQL_ROWS_END")
"""

proc = subprocess.run(
    ["docker", "exec", "bug_reproduction_worker", "python", "-c", sql_cmd],
    capture_output=True,
    text=True
)
print("\n--- RAW POSTGRES ROWS (CHRONOLOGICAL) ---")
print(proc.stdout)
if proc.stderr:
    print("STDERR:", proc.stderr)

# Calculate and display timestamps and deltas
new_items = data["items"][:new_count][::-1]
print("\n--- TIMESTAMPS & DELTAS ---")
for i, item in enumerate(new_items, 1):
    print(f"Row {i}: id={item['id']} | detected_at={item['detected_at']} | type={item['exception_type']} | message={item['exception_message'][:60]}")

if len(new_items) > 1:
    print("\n--- DELTA CALCULATION ---")
    for i in range(len(new_items) - 1):
        t1 = datetime.fromisoformat(new_items[i]['detected_at'])
        t2 = datetime.fromisoformat(new_items[i+1]['detected_at'])
        delta_sec = (t2 - t1).total_seconds()
        print(f"Delta between Row {i+1} and Row {i+2}: {delta_sec:.2f} seconds")

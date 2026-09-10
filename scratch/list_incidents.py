import os
from pathlib import Path
import psycopg2

env_path = Path(".env")
neon_url = ""
for line in env_path.read_text().splitlines():
    if "NEON_DATABASE_URL=" in line:
        neon_url = line.split("=", 1)[1].strip().strip("'\"")

conn = psycopg2.connect(neon_url)
with conn.cursor() as cur:
    cur.execute("SELECT id, detected_at, exception_type, exception_message, in_flight_run_ids FROM worker_incidents ORDER BY detected_at ASC")
    rows = cur.fetchall()
    print(f"Total rows: {len(rows)}")
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3][:40] if r[3] else ''} | {r[4]}")
conn.close()

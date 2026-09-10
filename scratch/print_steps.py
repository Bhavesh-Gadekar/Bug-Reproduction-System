from pathlib import Path
import os, psycopg2, json

env_path = Path(".env")
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip("'\"")

conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
cur = conn.cursor()

runs = [
    ("dateutil", "76210363-4d01-43ae-beca-272f841afd9e"),
    ("jinja2", "90380af6-ad6b-4621-a970-aa9d9530af02"),
    ("tqdm", "9c6c7ce2-3d77-425d-a584-f570208d6d2f")
]

for name, run_id in runs:
    cur.execute("""
        SELECT id, run_id, node_name, input, output, latency_ms, tokens_used, created_at
        FROM run_steps
        WHERE run_id = %s
        ORDER BY created_at ASC;
    """, (run_id,))
    rows = cur.fetchall()
    print(f"\n============================================================")
    print(f"RUN STEPS FOR {name.upper()} ({run_id}) - Total steps: {len(rows)}")
    print(f"============================================================")
    for r in rows:
        step_dict = {
            "id": str(r[0]),
            "run_id": str(r[1]),
            "node_name": r[2],
            "input": r[3],
            "output": r[4],
            "latency_ms": r[5],
            "tokens_used": r[6],
            "created_at": str(r[7])
        }
        print(json.dumps(step_dict, default=str))

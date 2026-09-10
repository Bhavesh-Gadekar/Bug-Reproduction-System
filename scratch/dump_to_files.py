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
    with open(f"scratch/layer2_{name}.txt", "w", encoding="utf-8") as f:
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
            f.write(json.dumps(step_dict, default=str) + "\n")

# Evaluation results for the 3 runs
cur.execute("""
    SELECT id, run_id, verdict, reviewer, notes
    FROM evaluation_results
    WHERE run_id IN %s;
""", (tuple(r[1] for r in runs),))
eval_rows = cur.fetchall()
with open("scratch/layer3_eval.txt", "w", encoding="utf-8") as f:
    for er in eval_rows:
        ed = {
            "id": str(er[0]),
            "run_id": str(er[1]),
            "verdict": er[2],
            "reviewer": er[3],
            "notes": er[4]
        }
        f.write(json.dumps(ed, default=str) + "\n")

# Item 3: Count and all rows
cur.execute("SELECT COUNT(*) FROM evaluation_results;")
count = cur.fetchone()[0]

cur.execute("""
    SELECT er.id, er.run_id, er.verdict, er.reviewer, rr.started_at
    FROM evaluation_results er
    LEFT JOIN reproduction_runs rr ON er.run_id = rr.id
    ORDER BY er.id ASC;
""")
all_rows = cur.fetchall()
with open("scratch/item3_output.txt", "w", encoding="utf-8") as f:
    f.write(f"COUNT: {count}\n")
    for row in all_rows:
        f.write(json.dumps({
            "eval_id": str(row[0]),
            "run_id": str(row[1]),
            "verdict": row[2],
            "reviewer": row[3],
            "started_at": str(row[4])
        }, default=str) + "\n")

print("Files written successfully.")

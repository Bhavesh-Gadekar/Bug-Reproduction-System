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

ROUND2_IDS = (
    'c9edc992-8c97-45d7-96e2-ebe730fc0aa1',
    '47795646-7d7e-40f2-b628-9b7a8e695d02',
    '76582c34-3289-4024-9cdb-3a4dffbb1241',
)

outlines = []

# ITEM 1A
outlines.append("=== ITEM 1A: evaluation_results for round-2 run_ids ===")
cur.execute("""
    SELECT er.id, er.run_id, er.verdict, er.reviewer
    FROM evaluation_results er
    WHERE er.run_id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    outlines.append(json.dumps({"eval_id": str(row[0]), "run_id": str(row[1]), "verdict": row[2], "reviewer": row[3]}, default=str))

# ITEM 1B
outlines.append("\n=== ITEM 1B: reproduction_runs for round-2 run_ids ===")
cur.execute("""
    SELECT id, status, started_at, completed_at, sandbox_container_id, candidate_produced, plausible_reproduced
    FROM reproduction_runs
    WHERE id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    outlines.append(json.dumps({
        "id": str(row[0]),
        "status": row[1],
        "started_at": str(row[2]),
        "completed_at": str(row[3]),
        "sandbox_container_id": row[4],
        "candidate_produced": row[5],
        "plausible_reproduced": row[6],
    }, default=str))

# ITEM 1C
outlines.append("\n=== ITEM 1C: run_steps for round-2 run_ids ===")
for run_id in ROUND2_IDS:
    cur.execute("""
        SELECT node_name, created_at
        FROM run_steps
        WHERE run_id = %s
        ORDER BY created_at ASC;
    """, (run_id,))
    rows = cur.fetchall()
    outlines.append(f"--- run_id={run_id} step count={len(rows)} ---")
    for r in rows:
        outlines.append(json.dumps({"node_name": r[0], "created_at": str(r[1])}, default=str))

# ITEM 2
outlines.append("\n=== ITEM 2: started_at null counts ===")
cur.execute("SELECT COUNT(*) FROM reproduction_runs WHERE started_at IS NOT NULL;")
outlines.append(f"Non-null started_at: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM reproduction_runs WHERE started_at IS NULL;")
outlines.append(f"Null started_at: {cur.fetchone()[0]}")

cur.execute("""
    SELECT id, status, started_at, completed_at
    FROM reproduction_runs
    ORDER BY completed_at DESC NULLS LAST
    LIMIT 8;
""")
outlines.append("Sample reproduction_runs (recent):")
for row in cur.fetchall():
    outlines.append(json.dumps({"id": str(row[0]), "status": row[1], "started_at": str(row[2]), "completed_at": str(row[3])}, default=str))

# ITEM 3: Only show the dep versions from stdout
outlines.append("\n=== ITEM 3: dependency version strings from dependency_install steps ===")
cur.execute("""
    SELECT run_id, output
    FROM run_steps
    WHERE node_name = 'dependency_install'
    ORDER BY created_at ASC;
""")
for r in cur.fetchall():
    out = r[1] or {}
    stdout = out.get("stdout", "") if isinstance(out, dict) else ""
    # Extract relevant "Successfully installed" line
    for line in stdout.splitlines():
        if "Successfully installed" in line or "Building wheel" in line:
            outlines.append(f"run_id={str(r[0])[:8]}: {line.strip()}")

conn.close()
outlines.append("Done.")

with open("scratch/day9_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(outlines))

print("Written to scratch/day9_output.txt")

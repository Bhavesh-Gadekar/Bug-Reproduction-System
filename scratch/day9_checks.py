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

# ============================================================
# ITEM 1: evaluation_results + reproduction_runs for round-2 runs
# ============================================================
print("\n=== ITEM 1A: evaluation_results for round-2 run_ids ===")
cur.execute("""
    SELECT er.id, er.run_id, er.verdict, er.reviewer
    FROM evaluation_results er
    WHERE er.run_id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    print(json.dumps({"eval_id": str(row[0]), "run_id": str(row[1]), "verdict": row[2], "reviewer": row[3]}, default=str))

print("\n=== ITEM 1B: reproduction_runs for round-2 run_ids ===")
cur.execute("""
    SELECT id, status, started_at, completed_at, sandbox_container_id, candidate_produced, plausible_reproduced
    FROM reproduction_runs
    WHERE id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    print(json.dumps({
        "id": str(row[0]),
        "status": row[1],
        "started_at": str(row[2]),
        "completed_at": str(row[3]),
        "sandbox_container_id": row[4],
        "candidate_produced": row[5],
        "plausible_reproduced": row[6],
    }, default=str))

print("\n=== ITEM 1C: run_steps for round-2 run_ids ===")
for run_id in ROUND2_IDS:
    cur.execute("""
        SELECT node_name, input, output, created_at
        FROM run_steps
        WHERE run_id = %s
        ORDER BY created_at ASC;
    """, (run_id,))
    rows = cur.fetchall()
    print(f"\n--- run_steps for {run_id} (count={len(rows)}) ---")
    for r in rows:
        print(json.dumps({"node_name": r[0], "input": r[1], "output": r[2], "created_at": str(r[3])}, default=str))

# ============================================================
# ITEM 2: started_at is NULL across ALL reproduction_runs
# ============================================================
print("\n=== ITEM 2: started_at NULL check across reproduction_runs ===")
cur.execute("""
    SELECT id, status, started_at, completed_at
    FROM reproduction_runs
    ORDER BY completed_at DESC
    LIMIT 15;
""")
for row in cur.fetchall():
    print(json.dumps({
        "id": str(row[0]),
        "status": row[1],
        "started_at": str(row[2]),
        "completed_at": str(row[3]),
    }, default=str))

print("\n=== ITEM 2B: COUNT with non-null started_at ===")
cur.execute("SELECT COUNT(*) FROM reproduction_runs WHERE started_at IS NOT NULL;")
print("Non-null started_at count:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM reproduction_runs WHERE started_at IS NULL;")
print("Null started_at count:", cur.fetchone()[0])

# ============================================================
# ITEM 3: repo_analysis output for all runs — check actual_commit_sha and version
# ============================================================
print("\n=== ITEM 3: repo_analysis + dependency_install steps for ALL runs (version info) ===")
cur.execute("""
    SELECT run_id, node_name, input, output, created_at
    FROM run_steps
    WHERE node_name IN ('repo_analysis', 'dependency_install')
    ORDER BY created_at ASC;
""")
for r in cur.fetchall():
    print(json.dumps({"run_id": str(r[0]), "node_name": r[1], "input": r[2], "output": r[3], "created_at": str(r[4])}, default=str))

conn.close()
print("\nDone.")

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

# ITEM 1: Re-tag these evaluation_results rows with reviewer = 'automated_benchmark_pre_fix_round2'
# This excludes them from correct BRT calculations while keeping the data for audit.
print("=== ITEM 1: Retagging round-2 evaluation_results rows ===")
cur.execute("""
    UPDATE evaluation_results
    SET reviewer = 'automated_benchmark_pre_fix_round2'
    WHERE run_id IN %s;
""", (ROUND2_IDS,))
print(f"  Rows updated: {cur.rowcount}")

# Verify
cur.execute("""
    SELECT id, run_id, verdict, reviewer FROM evaluation_results WHERE run_id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    print(json.dumps({"eval_id": str(row[0]), "run_id": str(row[1]), "verdict": row[2], "reviewer": row[3]}))

# ITEM 2: Backfill started_at for completed runs using min(run_steps.created_at)
print("\n=== ITEM 2: Backfilling started_at from earliest run_step ===")
cur.execute("""
    UPDATE reproduction_runs rr
    SET started_at = sub.earliest_step
    FROM (
        SELECT run_id, MIN(created_at) AS earliest_step
        FROM run_steps
        GROUP BY run_id
    ) sub
    WHERE rr.id = sub.run_id
      AND rr.started_at IS NULL;
""")
print(f"  Rows backfilled: {cur.rowcount}")

# Verify
cur.execute("""
    SELECT id, status, started_at, completed_at
    FROM reproduction_runs
    WHERE started_at IS NOT NULL
    ORDER BY completed_at DESC NULLS LAST
    LIMIT 10;
""")
print("  Sample rows after backfill:")
for row in cur.fetchall():
    print(json.dumps({"id": str(row[0]), "status": row[1], "started_at": str(row[2]), "completed_at": str(row[3])}))

cur.execute("SELECT COUNT(*) FROM reproduction_runs WHERE started_at IS NULL;")
print(f"  Remaining NULL started_at: {cur.fetchone()[0]}")

conn.commit()
conn.close()
print("\nDone. Commit succeeded.")

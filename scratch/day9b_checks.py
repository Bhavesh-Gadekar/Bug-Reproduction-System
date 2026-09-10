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

# ============================================================
# ITEM 1: Pull exact persist output for the 3 errored runs
# ============================================================
ROUND2_IDS = (
    'c9edc992-8c97-45d7-96e2-ebe730fc0aa1',
    '47795646-7d7e-40f2-b628-9b7a8e695d02',
    '76582c34-3289-4024-9cdb-3a4dffbb1241',
)

print("=== ITEM 1: persist step output for errored runs ===")
cur.execute("""
    SELECT run_id, input, output
    FROM run_steps
    WHERE node_name = 'persist' AND run_id IN %s;
""", (ROUND2_IDS,))
for row in cur.fetchall():
    print(f"\nrun_id={row[0]}")
    print(f"  input:  {json.dumps(row[1])}")
    print(f"  output: {json.dumps(row[2])}")

# ============================================================
# ITEM 2: Pull all 8 analyzing runs, get is_stale info
# ============================================================
print("\n\n=== ITEM 2: All 'analyzing' runs ===")
cur.execute("""
    SELECT id, status, started_at, updated_at
    FROM reproduction_runs
    WHERE status = 'analyzing'
    ORDER BY started_at ASC;
""")
analyzing_rows = cur.fetchall()
print(f"Count: {len(analyzing_rows)}")
import datetime
now = datetime.datetime.now(tz=datetime.timezone.utc)
STALE_THRESHOLD_SECONDS = 300

for row in analyzing_rows:
    run_id = row[0]
    status = row[1]
    started_at = row[2]
    updated_at = row[3]

    # Compute staleness from last updated_at or started_at
    last_activity = updated_at or started_at
    if last_activity:
        age_seconds = (now - last_activity).total_seconds()
        is_stale = age_seconds > STALE_THRESHOLD_SECONDS
        stale_reason = f"last activity {int(age_seconds)}s ago (>{STALE_THRESHOLD_SECONDS}s threshold)" if is_stale else None
    else:
        age_seconds = None
        is_stale = False
        stale_reason = None

    # Get latest run_steps timestamp for this run
    cur.execute("""
        SELECT MAX(created_at), COUNT(*) FROM run_steps WHERE run_id = %s;
    """, (str(run_id),))
    step_row = cur.fetchone()
    last_step_at = step_row[0]
    step_count = step_row[1]

    if last_step_at:
        step_age = (now - last_step_at).total_seconds()
        is_stale_from_steps = step_age > STALE_THRESHOLD_SECONDS
    else:
        step_age = None
        is_stale_from_steps = False

    print(json.dumps({
        "id": str(run_id),
        "status": status,
        "started_at": str(started_at),
        "updated_at": str(updated_at),
        "last_step_at": str(last_step_at),
        "step_count": step_count,
        "age_since_last_step_seconds": int(step_age) if step_age else None,
        "is_stale": is_stale_from_steps,
        "stale_reason": f"last run_step {int(step_age)}s ago" if is_stale_from_steps else "active or no steps",
    }, default=str))

# ============================================================
# ITEM 3: reproduction_run_status ENUM values
# ============================================================
print("\n\n=== ITEM 3: reproduction_run_status ENUM values in DB ===")
cur.execute("""
    SELECT enumlabel
    FROM pg_enum
    JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
    WHERE pg_type.typname = 'reproduction_run_status'
    ORDER BY enumsortorder;
""")
enum_vals = [row[0] for row in cur.fetchall()]
print(f"  ENUM values: {enum_vals}")

conn.close()
print("\nDone.")

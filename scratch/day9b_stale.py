from pathlib import Path
import os, psycopg2, json, datetime

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

# Get columns
cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = 'reproduction_runs'
    ORDER BY ordinal_position;
""")
cols = [r[0] for r in cur.fetchall()]
print("reproduction_runs columns:", cols)

# ENUM values
cur.execute("""
    SELECT enumlabel
    FROM pg_enum
    JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
    WHERE pg_type.typname = 'reproduction_run_status'
    ORDER BY enumsortorder;
""")
print("ENUM values:", [r[0] for r in cur.fetchall()])

# Analyzing runs with staleness check
print("\n=== ITEM 2: Analyzing runs staleness ===")
cur.execute("""
    SELECT id, status, started_at, completed_at
    FROM reproduction_runs
    WHERE status = 'analyzing'
    ORDER BY started_at ASC;
""")
analyzing = cur.fetchall()
print(f"Count: {len(analyzing)}")

now = datetime.datetime.now(tz=datetime.timezone.utc)
STALE_SECONDS = 300

for row in analyzing:
    run_id, status, started_at, completed_at = row
    # latest run_step
    cur.execute("""
        SELECT MAX(created_at), COUNT(*) FROM run_steps WHERE run_id = %s;
    """, (str(run_id),))
    step_row = cur.fetchone()
    last_step_at = step_row[0]
    step_count = step_row[1]

    if last_step_at:
        step_age = (now - last_step_at).total_seconds()
        is_stale = step_age > STALE_SECONDS
        stale_reason = f"last run_step was {int(step_age)}s ago (>{STALE_SECONDS}s threshold)" if is_stale else None
    else:
        step_age = None
        is_stale = False
        stale_reason = "no run_steps found"

    print(json.dumps({
        "run_id": str(run_id),
        "status": status,
        "started_at": str(started_at),
        "last_step_at": str(last_step_at),
        "step_count": step_count,
        "age_since_last_step_s": int(step_age) if step_age else None,
        "is_stale": is_stale,
        "stale_reason": stale_reason,
    }, default=str))

conn.close()
print("\nDone.")

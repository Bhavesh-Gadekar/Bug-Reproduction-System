import os
import json
from pathlib import Path
import sqlalchemy as sa

env_path = Path(".env")
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.strip().split("=", 1)
            os.environ[k] = v.strip("'\"")

url = os.environ["NEON_DATABASE_URL"].replace("postgres://", "postgresql://", 1)
engine = sa.create_engine(url)

with engine.connect() as conn:
    rows = conn.execute(sa.text("""
        SELECT e.id, e.run_id, e.verdict, e.reviewer, e.notes,
               r.status as run_status, r.candidate_produced, r.plausible_reproduced
        FROM evaluation_results e
        LEFT JOIN reproduction_runs r ON e.run_id = r.id
        ORDER BY e.id
    """)).fetchall()
    print(f"Total evaluation_results rows: {len(rows)}")
    for r in rows:
        d = dict(r._mapping)
        # Convert UUIDs to string for JSON serialization
        for k, v in d.items():
            if hasattr(v, "__str__"):
                d[k] = str(v)
        print(json.dumps(d))

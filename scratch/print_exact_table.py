import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["NEON_DATABASE_URL"])
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, node_name, latency_ms, created_at
        FROM run_steps
        WHERE run_id = 'f76ee266-4d45-4f8e-806e-cc2273f05cca'
        ORDER BY created_at ASC
    """)).mappings().all()
    print(f"Total steps in DB: {len(rows)}")
    prev_time = None
    for i, r in enumerate(rows):
        gap = (r["created_at"] - prev_time).total_seconds() * 1000 if prev_time else 0.0
        print(f"[{i:2d}] {r['node_name']:20s} | latency_ms: {r['latency_ms']:6d} | created_at: {r['created_at']} | gap: {gap:9.2f}ms")
        prev_time = r["created_at"]

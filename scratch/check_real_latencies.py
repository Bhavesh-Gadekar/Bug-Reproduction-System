import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["NEON_DATABASE_URL"])
with engine.connect() as conn:
    print("=== GENUINE RUN STEPS TIMESTAMPS & LATENCIES (Run f76ee266) ===")
    rows = conn.execute(text("""
        SELECT node_name, latency_ms, created_at
        FROM run_steps
        WHERE run_id = 'f76ee266-4d45-4f8e-806e-cc2273f05cca'
        ORDER BY created_at ASC
    """)).mappings().all()
    prev_time = None
    for r in rows:
        gap = (r["created_at"] - prev_time).total_seconds() * 1000 if prev_time else 0
        print(f"{r['node_name']:20s} | latency: {r['latency_ms']:5d}ms | created_at: {r['created_at']} | gap: {gap:7.1f}ms")
        prev_time = r["created_at"]

import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["NEON_DATABASE_URL"])
run_id = '4618d11e-6cce-4ab4-a3d3-30cd8d7f6d0e'
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, node_name, input, output, latency_ms, created_at
        FROM run_steps 
        WHERE run_id = :run_id
        ORDER BY created_at ASC
    """), {"run_id": run_id}).mappings().all()
    print(f"TOTAL RUN_STEPS IN NEON DB: {len(rows)}")
    for r in rows:
        print(f"=== STEP: {r['node_name']} (id={r['id']}, latency={r['latency_ms']}ms, created_at={r['created_at']}) ===")
        print("INPUT:", json.dumps(r["input"], indent=2))
        print("OUTPUT:", json.dumps(r["output"], indent=2))
        print()

    run = conn.execute(text("""
        SELECT * FROM reproduction_runs WHERE id = :run_id
    """), {"run_id": run_id}).mappings().first()
    print("=== REPRODUCTION RUN ROW ===")
    for k, v in run.items():
        print(f"  {k}: {v}")
    print()

    artifacts = conn.execute(text("""
        SELECT id, type, storage_path, status, error, created_at 
        FROM artifacts 
        WHERE run_id = '11a88139-3739-4da5-b473-5f541edb99e9'
        ORDER BY created_at DESC
    """)).mappings().all()
    print("=== ARTIFACTS IN NEON DB ===")
    for a in artifacts:
        print(f"  [{a['type']}] id={a['id']} status={a['status']} error={a['error']}")
        print(f"     path={a['storage_path']}")

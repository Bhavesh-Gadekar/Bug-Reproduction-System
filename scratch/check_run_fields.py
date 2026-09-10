import sqlalchemy as sa

db_url = "postgresql://neondb_owner:npg_3MmYAjNI1Rug@ep-raspy-tooth-axajmdfd-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
engine = sa.create_engine(db_url)
with engine.connect() as conn:
    row = conn.execute(sa.text("""
        SELECT id, status, candidate_produced, plausible_reproduced, persist_error, started_at, completed_at, sandbox_container_id 
        FROM reproduction_runs 
        WHERE id = 'e574a420-4030-46c0-bef0-0c059953c332'
    """)).mappings().first()
    if row:
        for k, v in row.items():
            print(f"{k}: {repr(v)}")
    else:
        print("Run not found!")

    # Check artifacts
    arts = conn.execute(sa.text("""
        SELECT id, type, storage_path, status, error, created_at 
        FROM artifacts 
        WHERE run_id = 'e574a420-4030-46c0-bef0-0c059953c332'
    """)).mappings().all()
    print(f"\nArtifacts ({len(arts)}):")
    for a in arts:
        print(dict(a))

    # Check last steps
    steps = conn.execute(sa.text("""
        SELECT node_name, output, latency_ms, created_at 
        FROM run_steps 
        WHERE run_id = 'e574a420-4030-46c0-bef0-0c059953c332' 
        ORDER BY created_at DESC 
        LIMIT 3
    """)).mappings().all()
    print("\nLast 3 steps:")
    for s in steps:
        print(f"[{s['node_name']}] latency={s['latency_ms']}ms output={s['output']}")

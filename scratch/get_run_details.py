import sqlalchemy as sa
import os

url = os.environ.get("NEON_DATABASE_URL").replace("postgres://", "postgresql://")
connect_args = {}
try:
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname:
        connect_args["hostaddr"] = socket.gethostbyname(parsed.hostname)
except Exception:
    pass

engine = sa.create_engine(url, pool_pre_ping=True, connect_args=connect_args)
run_id = "3291ad5e-e5f9-43be-ae61-baebd9cb7087"

with engine.connect() as conn:
    run = conn.execute(sa.text("SELECT id, status, candidate_produced, plausible_reproduced, started_at, completed_at FROM reproduction_runs WHERE id = :id"), {"id": run_id}).fetchone()
    print("RUN DETAILS:")
    print(dict(run._mapping))

    steps = conn.execute(sa.text("SELECT node_name, latency_ms, created_at, output FROM run_steps WHERE run_id = :id ORDER BY created_at ASC"), {"id": run_id}).fetchall()
    print(f"\nRAW RUN STEPS ({len(steps)} steps):")
    for s in steps:
        out_str = str(s.output)[:80] if s.output else ""
        print(f"{s.node_name:20} | latency={s.latency_ms:6}ms | created_at={s.created_at} | output_summary={out_str}")

    artifacts = conn.execute(sa.text("SELECT type, status, storage_path FROM artifacts WHERE run_id = :id"), {"id": run_id}).fetchall()
    print(f"\nARTIFACTS ({len(artifacts)} items):")
    for a in artifacts:
        print(f"{str(a.type):15} | status={a.status:10} | path={a.storage_path}")

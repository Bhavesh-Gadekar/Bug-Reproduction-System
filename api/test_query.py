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
with engine.connect() as conn:
    rows = conn.execute(sa.text("""
        SELECT e.id, e.run_id, e.reviewer, r.id as r_id
        FROM evaluation_results e
        LEFT JOIN reproduction_runs r ON e.run_id = r.id
        WHERE e.reviewer LIKE 'automated_benchmark%';
    """)).fetchall()
    print("Matching rows:", len(rows))
    for r in rows:
        print(r.run_id, r.reviewer, "has_run:", bool(r.r_id))

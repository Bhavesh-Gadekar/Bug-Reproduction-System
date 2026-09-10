from app.core.config import get_worker_settings
import psycopg

s = get_worker_settings()
conn = psycopg.connect(s.NEON_DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT id, status, started_at, completed_at FROM reproduction_runs WHERE id = '4026a195-23c6-498c-9787-22a6ed11eb86'")
print("RUN:", cur.fetchall())
cur.execute("SELECT node_name, created_at FROM run_steps WHERE run_id = '4026a195-23c6-498c-9787-22a6ed11eb86' ORDER BY created_at ASC")
print("STEPS:", cur.fetchall())

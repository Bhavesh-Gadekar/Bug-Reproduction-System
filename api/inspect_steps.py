import sqlalchemy as sa
import os

url = os.environ.get("NEON_DATABASE_URL").replace("postgres://", "postgresql://")
engine = sa.create_engine(url)
with engine.connect() as conn:
    evals = conn.execute(sa.text("SELECT id, run_id, verdict FROM evaluation_results ORDER BY id;")).fetchall()
    for idx, e in enumerate(evals, 1):
        run = conn.execute(sa.text("SELECT candidate_produced, plausible_reproduced, status, persist_error FROM reproduction_runs WHERE id = :id"), {"id": e.run_id}).fetchone()
        v_steps = conn.execute(sa.text("SELECT output FROM run_steps WHERE run_id = :id AND node_name = 'verdict'"), {"id": e.run_id}).fetchall()
        v_repro = any(s.output and s.output.get("reproduced") for s in v_steps)
        s_steps = conn.execute(sa.text("SELECT output FROM run_steps WHERE run_id = :id AND node_name = 'script_gen'"), {"id": e.run_id}).fetchall()
        has_script = any(s.output and s.output.get("script") for s in s_steps)
        print(f"[{idx}] Run {str(e.run_id)[:8]} | DB Cand: {str(run.candidate_produced):5} | Has Script: {str(has_script):5} | Step Repro: {str(v_repro):5} | Status: {run.status}")

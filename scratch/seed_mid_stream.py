import uuid, os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

run_id = '013c0fd0-729c-47f9-999a-f9550426b249'
engine = create_engine(os.environ['NEON_DATABASE_URL'])
with engine.begin() as conn:
    conn.execute(
        text("UPDATE reproduction_runs SET status = 'analyzing', started_at = :now, model_version = 'gemini-2.5-pro' WHERE id = :run_id"),
        {"run_id": run_id, "now": datetime.now(timezone.utc)}
    )

    s1 = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO run_steps (id, run_id, node_name, input, output, tokens_used, latency_ms, created_at) VALUES (:id, :run_id, 'ingest', '{\"title\": \"ZeroDivisionError in matrix inverse\"}', '{\"status\": \"accepted\", \"language\": \"python\"}', 120, 310, :now)"),
        {"id": s1, "run_id": run_id, "now": datetime.now(timezone.utc)}
    )

    s2 = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO run_steps (id, run_id, node_name, input, output, tokens_used, latency_ms, created_at) VALUES (:id, :run_id, 'repo_analysis', '{\"git_url\": \"https://github.com/dateutil/dateutil\"}', '{\"entrypoints\": [\"matrix_solve.py\"], \"framework\": \"pytest\"}', 480, 920, :now)"),
        {"id": s2, "run_id": run_id, "now": datetime.now(timezone.utc)}
    )

    s3 = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO run_steps (id, run_id, node_name, input, output, tokens_used, latency_ms, created_at) VALUES (:id, :run_id, 'hypothesis_gen', '{\"issue\": \"ZeroDivisionError\"}', '{\"hypothesis\": \"Singular matrix determinants evaluate to 0.0 leading to unhandled division in inverse computation.\"}', 650, 1420, :now)"),
        {"id": s3, "run_id": run_id, "now": datetime.now(timezone.utc)}
    )

print("Updated run 013c0fd0-729c-47f9-999a-f9550426b249 to mid-stream analyzing with 3 active steps!")

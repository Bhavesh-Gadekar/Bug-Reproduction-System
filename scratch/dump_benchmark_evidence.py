import json
import os
from pathlib import Path
import dotenv
import httpx
import sqlalchemy as sa

dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
engine = sa.create_engine(os.getenv("NEON_DATABASE_URL"))

run_ids = [
    "977dcaae-e63a-4c2a-9321-195fad1810f8",  # dateutil
    "67a4761a-6759-4b0f-9deb-4f929cbf6043",  # jinja2
    "8e3c7e38-73df-4eb0-b553-2ded05550364",  # tqdm
]

print("=" * 70)
print("LAYER 1: RAW JSON API RESPONSES FOR EACH OF THE 3 SUBMITTED RUNS")
print("=" * 70)
with httpx.Client(timeout=15.0) as client:
    for rid in run_ids:
        r = client.get(f"http://127.0.0.1:8000/api/runs/{rid}")
        data = r.json()
        print(f"\n>>> GET /api/runs/{rid} (HTTP {r.status_code})")
        # Print the complete response, truncating large steps/artifacts if any
        summary_payload = {
            "id": data["id"],
            "bug_report_id": data["bug_report_id"],
            "status": data["status"],
            "raw_status": data["raw_status"],
            "is_stale": data["is_stale"],
            "stale_reason": data.get("stale_reason"),
            "model_version": data.get("model_version"),
            "prompt_version": data.get("prompt_version"),
            "candidate_produced": data["candidate_produced"],
            "plausible_reproduced": data["plausible_reproduced"],
            "started_at": data["started_at"],
            "completed_at": data["completed_at"],
            "persist_error": data["persist_error"],
            "total_steps_recorded": len(data.get("steps", [])),
            "artifacts_recorded": [
                {"type": a["type"], "storage_path": a["storage_path"], "status": a["status"]}
                for a in data.get("artifacts", [])
            ],
            "bug_report": data.get("bug_report", {}),
        }
        print(json.dumps(summary_payload, indent=2))

print("\n" + "=" * 70)
print("LAYER 2: RAW RUN_STEPS ROWS (repo_analysis and sandbox_exec steps)")
print("=" * 70)
with engine.connect() as conn:
    for rid in run_ids:
        print(f"\n>>> RUN_STEPS FOR RUN {rid}")
        rows = conn.execute(
            sa.text("""
                SELECT node_name, latency_ms, tokens_used, output
                FROM run_steps
                WHERE run_id = :rid AND node_name IN ('repo_analysis', 'sandbox_exec')
                ORDER BY created_at ASC
            """),
            {"rid": rid},
        ).fetchall()
        for node_name, latency_ms, tokens_used, output in rows:
            print(f"\n  [STEP: {node_name}] latency={latency_ms}ms tokens={tokens_used}")
            print(f"  OUTPUT:")
            print(json.dumps(output, indent=4))

print("\n" + "=" * 70)
print("LAYER 3: RAW EVALUATION_RESULTS ROWS FROM NEON DB + SUMMARY OUTPUT")
print("=" * 70)
with engine.connect() as conn:
    rows = conn.execute(
        sa.text("""
            SELECT id, run_id, verdict, reviewer, notes
            FROM evaluation_results
            WHERE reviewer = 'automated_benchmark'
            ORDER BY run_id ASC
        """)
    ).fetchall()
    for row in rows:
        print(f"\n  EVAL_ID:  {row[0]}")
        print(f"  RUN_ID:   {row[1]}")
        print(f"  VERDICT:  {row[2]}")
        print(f"  REVIEWER: {row[3]}")
        print(f"  NOTES:")
        print("  " + "\n  ".join(str(row[4]).splitlines()))
        print("  " + "-" * 60)

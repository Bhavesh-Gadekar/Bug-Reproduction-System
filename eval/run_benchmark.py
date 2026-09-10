#!/usr/bin/env python3
"""Eval Harness CLI Benchmark runner and summary reporter.

Submits fixtures via real HTTP POST /api/bug-reports, monitors execution
progression, validates against staleness, classifies verdicts, records
evaluation_results with audit trails into Neon DB, and reports BRT metrics.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import functools
import httpx
import sqlalchemy as sa

# Ensure all prints flush immediately for background task and pipe monitoring
print = functools.partial(print, flush=True)


def _load_env_file(env_path: Path) -> None:
    """Parse .env file manually into os.environ if dotenv not installed."""
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val


def _get_db_engine():
    """Create SQLAlchemy engine using NEON_DATABASE_URL from environment."""
    project_root = Path(__file__).resolve().parent.parent
    _load_env_file(project_root / ".env")

    url = os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise RuntimeError("NEON_DATABASE_URL is not set in environment or .env file.")

    # Convert to standard postgresql:// for SQLAlchemy driver
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    connect_args = {}
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname:
            connect_args["hostaddr"] = socket.gethostbyname(parsed.hostname)
    except Exception:
        pass

    return sa.create_engine(url, pool_pre_ping=True, connect_args=connect_args)


TERMINAL_STATUSES = {"succeeded", "failed", "error", "timed_out"}


def run_benchmark(
    api_url: str = "http://127.0.0.1:8000",
    fixtures_dir: str = "eval/fixtures",
    poll_interval: int = 5,
    stale_threshold: int = 300,
    max_wait_seconds: int = 900,
) -> list[dict[str, Any]]:
    """Submit each fixture, poll to terminal/stale state, classify and record."""
    fixtures_path = Path(fixtures_dir)
    if not fixtures_path.is_absolute():
        fixtures_path = Path(__file__).resolve().parent.parent / fixtures_dir

    fixture_files = sorted(fixtures_path.glob("*.json"))
    if not fixture_files:
        print(f"Error: No fixture files found in {fixtures_path}")
        sys.exit(1)

    print(f"============================================================")
    print(f"  STARTING BENCHMARK RUN ({len(fixture_files)} fixtures)")
    print(f"  API URL:          {api_url}")
    print(f"  Fixtures dir:     {fixtures_path}")
    print(f"  Stale threshold:  {stale_threshold}s")
    print(f"============================================================\n")

    engine = _get_db_engine()
    results = []

    for idx, fpath in enumerate(fixture_files, start=1):
        print(f"\n[{idx}/{len(fixture_files)}] Processing fixture: {fpath.name}")
        with open(fpath, "r", encoding="utf-8") as f:
            fixture = json.load(f)

        # 1. Prepare BugReportCreate payload
        payload = {
            "title": fpath.stem.replace("_", " ").title(),
            "description": f"{fixture.get('bug_description', '')}\nSource: {fixture.get('source_url', '')}",
            "raw_stack_trace": fixture.get("expected_failure_signature", ""),
            "repo": {
                "git_url": fixture.get("repo_url", ""),
                "base_commit_sha": fixture.get("commit_sha", ""),
                "branch": "main",
            },
            "max_hypotheses": 3,
        }

        # 2. Submit via real HTTP POST /api/bug-reports
        print(f"  Submitting to POST {api_url}/api/bug-reports ...")
        submit_resp_data = None
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{api_url}/api/bug-reports", json=payload)
            if resp.status_code != 202:
                print(f"  [ERROR] Failed to submit: HTTP {resp.status_code} - {resp.text}")
                continue
            submit_resp_data = resp.json()

        run_id = submit_resp_data["run_id"]
        bug_report_id = submit_resp_data["bug_report_id"]
        print(f"  [ACCEPTED] HTTP {resp.status_code}")
        print(f"  Run ID:        {run_id}")
        print(f"  Bug Report ID: {bug_report_id}")
        print(f"  Raw response:  {json.dumps(submit_resp_data)}")

        # 3. Poll for completion or staleness
        print(f"  Polling run progression (checking every {poll_interval}s)...")
        elapsed = 0
        run_data = None
        is_stale_detected = False
        stale_reason_str = None

        with httpx.Client(timeout=30.0) as client:
            while elapsed < max_wait_seconds:
                time.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    poll_resp = client.get(
                        f"{api_url}/api/runs/{run_id}?stale_threshold_seconds={stale_threshold}"
                    )
                    if poll_resp.status_code != 200:
                        print(f"    [T+{elapsed}s] Poll warning: HTTP {poll_resp.status_code}")
                        continue

                    run_data = poll_resp.json()
                    current_status = run_data.get("status")
                    raw_status = run_data.get("raw_status", current_status)
                    is_stale = run_data.get("is_stale", False)
                    stale_reason = run_data.get("stale_reason")
                    steps_count = len(run_data.get("steps", []))

                    print(
                        f"    [T+{elapsed}s] status={current_status} raw_status={raw_status} "
                        f"steps={steps_count} is_stale={is_stale}"
                    )

                    # Check for staleness
                    if is_stale:
                        print(f"  [STALE DETECTED] Run flagged as stale: {stale_reason}")
                        is_stale_detected = True
                        stale_reason_str = stale_reason
                        break

                    # Check for terminal status
                    if current_status in TERMINAL_STATUSES:
                        print(f"  [TERMINAL] Run reached terminal status: {current_status}")
                        break

                except Exception as e:
                    print(f"    [T+{elapsed}s] Poll exception: {e}")

        if not run_data:
            print(f"  [ERROR] No data retrieved for run {run_id}")
            continue

        # 4. Extract captured output from sandbox_exec step
        captured_sandbox_output = ""
        for step in run_data.get("steps", []):
            if step.get("node_name") == "sandbox_exec":
                out = step.get("output", {})
                stdout = out.get("stdout", "")
                stderr = out.get("stderr", "")
                captured_sandbox_output += f"--- sandbox_exec output ---\nstdout:\n{stdout}\nstderr:\n{stderr}\n"

        if not captured_sandbox_output:
            captured_sandbox_output = "(No sandbox_exec execution records captured)"

        # 5. Result Classification
        plausible_reproduced = run_data.get("plausible_reproduced", False)
        candidate_produced = run_data.get("candidate_produced", False)
        ground_truth = fixture.get("ground_truth_reproducible", True)

        if is_stale_detected:
            verdict = "false_negative"
            notes = (
                f"[STALE/INCONCLUSIVE] Run failed to reach terminal state within threshold.\n"
                f"Reason: {stale_reason_str}\n\n"
                f"Expected Failure Signature:\n{fixture.get('expected_failure_signature')}\n\n"
                f"Actual Sandbox Output:\n{captured_sandbox_output}"
            )
        else:
            if plausible_reproduced and ground_truth:
                verdict = "true_positive"
            elif plausible_reproduced and not ground_truth:
                verdict = "false_positive"
            else:
                verdict = "false_negative"

            notes = (
                f"Expected Failure Signature:\n{fixture.get('expected_failure_signature')}\n\n"
                f"Actual Sandbox Output:\n{captured_sandbox_output}"
            )

        # 6. Write evaluation_results row into Neon DB
        eval_id = uuid.uuid4()
        run_uuid = uuid.UUID(run_id)
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO evaluation_results (
                        id, run_id, verdict, reviewer, notes
                    ) VALUES (
                        :id, :run_id, CAST(:verdict AS evaluation_verdict), :reviewer, :notes
                    )
                """),
                {
                    "id": eval_id,
                    "run_id": run_uuid,
                    "verdict": verdict,
                    "reviewer": "automated_benchmark",
                    "notes": notes,
                }
            )

        print(f"  [EVALUATION SAVED] evaluation_result_id={eval_id}")
        print(f"  Verdict:              {verdict}")
        print(f"  Candidate Produced:   {candidate_produced}")
        print(f"  Plausible Reproduced: {plausible_reproduced}")
        print(f"  Reviewer:             automated_benchmark")

        results.append({
            "fixture": fpath.name,
            "run_id": run_id,
            "submit_response": submit_resp_data,
            "run_data": run_data,
            "verdict": verdict,
            "candidate_produced": candidate_produced,
            "plausible_reproduced": plausible_reproduced,
            "is_stale": is_stale_detected,
        })

    print(f"\n============================================================")
    print(f"  ALL {len(results)} BENCHMARK FIXTURES COMPLETED")
    print(f"============================================================\n")

    current_rids = [r["run_id"] for r in results]
    summarize_benchmark(current_run_ids=current_rids)
    return results


def summarize_benchmark(current_run_ids: list[str] | None = None) -> None:
    """Print Candidate BRT, Plausible BRT, and stale counts from Neon DB."""
    engine = _get_db_engine()

    def _get_metrics(run_ids_filter: list[str] | None = None):
        where_clauses = ["(e.reviewer LIKE 'automated_benchmark%')"]
        params = {}
        if run_ids_filter:
            where_clauses.append("e.run_id IN :run_ids")
            params["run_ids"] = tuple(uuid.UUID(rid) for rid in run_ids_filter)

        query = sa.text(f"""
            SELECT 
                e.id AS eval_id,
                e.run_id,
                e.verdict AS stored_verdict,
                e.notes,
                r.candidate_produced,
                r.plausible_reproduced,
                COALESCE(BOOL_OR(
                    rs.output->>'reproduced' = 'true' 
                    OR rs.output->>'verdict' = 'matched'
                ), false) AS step_matched,
                COUNT(rs.id) > 0 AS has_verdict_step
            FROM evaluation_results e
            JOIN reproduction_runs r ON e.run_id = r.id
            LEFT JOIN run_steps rs ON e.run_id = rs.run_id AND rs.node_name = 'verdict'
            WHERE {' AND '.join(where_clauses)}
            GROUP BY e.id, e.run_id, e.verdict, e.notes, r.candidate_produced, r.plausible_reproduced
        """)

        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()

        from collections import namedtuple
        MetricsRow = namedtuple("MetricsRow", [
            "total_evaluated", "candidate_count", "plausible_count",
            "true_positives", "false_positives", "false_negatives", "stale_inconclusive_count"
        ])

        total = len(rows)
        cand_cnt = 0
        plaus_cnt = 0
        tp = 0
        fp = 0
        fn = 0
        stale = 0

        for r in rows:
            is_stale = bool(r.notes and "[STALE/INCONCLUSIVE]" in r.notes)
            if is_stale:
                stale += 1

            if r.has_verdict_step:
                if r.step_matched:
                    tp += 1
                    plaus_cnt += 1
                    cand_cnt += 1
                else:
                    fn += 1
                    if r.candidate_produced:
                        cand_cnt += 1
            else:
                v_str = str(r.stored_verdict)
                if v_str == "true_positive":
                    tp += 1
                elif v_str == "false_positive":
                    fp += 1
                else:
                    fn += 1
                if r.candidate_produced:
                    cand_cnt += 1
                if r.plausible_reproduced:
                    plaus_cnt += 1

        return MetricsRow(
            total_evaluated=total,
            candidate_count=cand_cnt,
            plausible_count=plaus_cnt,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            stale_inconclusive_count=stale,
        )

    if current_run_ids:
        row = _get_metrics(current_run_ids)
        total = row.total_evaluated or 0
        candidate_count = row.candidate_count or 0
        plausible_count = row.plausible_count or 0
        tp = row.true_positives or 0
        fp = row.false_positives or 0
        fn = row.false_negatives or 0
        stale_count = row.stale_inconclusive_count or 0

        candidate_brt = (candidate_count / total * 100.0) if total > 0 else 0.0
        plausible_brt = (plausible_count / total * 100.0) if total > 0 else 0.0

        print("============================================================")
        print("          CURRENT BENCHMARK SUITE RUN SUMMARY               ")
        print(f"             (Runs in this batch: {len(current_run_ids)})                  ")
        print("============================================================")
        print(f"  Total Runs Evaluated:      {total}")
        print(f"  Candidate Produced:        {candidate_count} / {total} ({candidate_brt:.1f}%)")
        print(f"  Candidate BRT Rate:        {candidate_brt:.1f}%")
        print(f"  Plausible Reproduced:      {plausible_count} / {total} ({plausible_brt:.1f}%)")
        print(f"  Plausible BRT Rate:        {plausible_brt:.1f}%")
        print(f"  Stale / Inconclusive Runs: {stale_count}")
        print("------------------------------------------------------------")
        print("  Classification Breakdown (vs Ground Truth):")
        print(f"    - True Positives (TP):   {tp}")
        print(f"    - False Positives (FP):  {fp}")
        print(f"    - False Negatives (FN):  {fn}")
        print("============================================================\n")

    # Cumulative all-time summary
    row_all = _get_metrics(None)
    total_all = row_all.total_evaluated or 0
    candidate_all = row_all.candidate_count or 0
    plausible_all = row_all.plausible_count or 0
    tp_all = row_all.true_positives or 0
    fp_all = row_all.false_positives or 0
    fn_all = row_all.false_negatives or 0
    stale_all = row_all.stale_inconclusive_count or 0

    c_brt_all = (candidate_all / total_all * 100.0) if total_all > 0 else 0.0
    p_brt_all = (plausible_all / total_all * 100.0) if total_all > 0 else 0.0

    print("============================================================")
    print("      ALL-TIME CUMULATIVE BENCHMARK EVALUATION SUMMARY      ")
    print("      (Source: Neon DB evaluation_results + runs)          ")
    print("============================================================")
    print(f"  Total Historical Runs:     {total_all}")
    print(f"  Candidate Produced:        {candidate_all} / {total_all} ({c_brt_all:.1f}%)")
    print(f"  Candidate BRT Rate:        {c_brt_all:.1f}%")
    print(f"  Plausible Reproduced:      {plausible_all} / {total_all} ({p_brt_all:.1f}%)")
    print(f"  Plausible BRT Rate:        {p_brt_all:.1f}%")
    print(f"  Stale / Inconclusive Runs: {stale_all}")
    print("------------------------------------------------------------")
    print("  Classification Breakdown (vs Ground Truth):")
    print(f"    - True Positives (TP):   {tp_all}")
    print(f"    - False Positives (FP):  {fp_all}")
    print(f"    - False Negatives (FN):  {fn_all}")
    print("============================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval Harness Benchmark CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run benchmark command
    run_parser = subparsers.add_parser("run", help="Run benchmark on fixtures")
    run_parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="API Base URL")
    run_parser.add_argument("--fixtures-dir", default="eval/fixtures", help="Directory of fixtures")
    run_parser.add_argument("--poll-interval", type=int, default=5, help="Poll interval in seconds")
    run_parser.add_argument("--stale-threshold", type=int, default=300, help="Staleness threshold in seconds")
    run_parser.add_argument("--timeout", type=int, default=900, help="Max wait seconds per run")

    # Summarize command
    subparsers.add_parser("summarize", help="Print summary from Neon DB")

    args = parser.parse_args()

    if args.command == "summarize":
        summarize_benchmark()
    elif args.command == "run" or args.command is None:
        run_benchmark(
            api_url=getattr(args, "api_url", "http://127.0.0.1:8000"),
            fixtures_dir=getattr(args, "fixtures_dir", "eval/fixtures"),
            poll_interval=getattr(args, "poll_interval", 5),
            stale_threshold=getattr(args, "stale_threshold", 300),
            max_wait_seconds=getattr(args, "timeout", 900),
        )


if __name__ == "__main__":
    main()

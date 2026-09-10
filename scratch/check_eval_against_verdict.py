import re
import urllib.request
import json

from app.graph.nodes.verdict import extract_primary_error, extract_signature_keywords

data = json.loads(urllib.request.urlopen("http://bug_reproduction_api:8000/api/metrics/brt").read())
print(f"Auditing all {len(data['raw_evaluations'])} evaluation_results rows against current verdict.py logic:\n")

discrepancies = 0

for idx, r in enumerate(data["raw_evaluations"], 1):
    notes = r.get("notes") or ""
    parts = notes.split("Actual Sandbox Output:\n")
    if len(parts) != 2:
        print(f"[{idx}] Run {r['run_id'][:8]}: Note format inconclusive (stale/inconclusive)")
        continue
    expected_sig = parts[0].replace("Expected Failure Signature:\n", "").strip()
    actual_out = parts[1].strip()

    primary_error = extract_primary_error(expected_sig)
    keywords = extract_signature_keywords(expected_sig)

    combined_output = actual_out
    has_error_signature = (
        "Traceback" in combined_output
        or "Exception ignored" in combined_output
        or "Error:" in combined_output
    )

    if has_error_signature:
        if primary_error:
            primary_pattern = r"(?:^|\s|[\w.]*?\.)" + re.escape(primary_error) + r"\s*:"
            if re.search(primary_pattern, combined_output, re.MULTILINE) or f"{primary_error}:" in combined_output:
                verdict = "matched"
            else:
                verdict = "no_match"
        elif any(kw in combined_output for kw in keywords):
            verdict = "matched"
        else:
            verdict = "no_match"
    else:
        verdict = "no_match"

    reproduced_now = (verdict == "matched")
    db_plausible = r["plausible_reproduced"]
    db_verdict = r["verdict"]

    matches_db = (reproduced_now == db_plausible)
    if not matches_db:
        discrepancies += 1
        status_flag = "MISMATCH"
    else:
        status_flag = "OK"

    print(f"[{idx}] Run {r['run_id'][:8]} | DB verdict: {db_verdict:14} | DB plausible: {str(db_plausible):5} | Now matched: {str(reproduced_now):5} | Primary: {str(primary_error):18} | {status_flag}")
    if not matches_db:
        print(f"    Expected Primary: {primary_error}")
        print(f"    Actual out excerpt: {actual_out[:200]}...")

print(f"\nTotal rows audited: {len(data['raw_evaluations'])}")
print(f"Discrepancies found: {discrepancies}")

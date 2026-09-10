import urllib.request
import json

data = json.loads(urllib.request.urlopen("http://bug_reproduction_api:8000/api/metrics/brt").read())

print("TOP LEVEL METRICS:")
print(json.dumps({k: v for k, v in data.items() if k != "raw_evaluations"}, indent=2))

print("\nEVALUATIONS BREAKDOWN:")
for idx, r in enumerate(data["raw_evaluations"], 1):
    print(f"[{idx:2d}] {r['run_id'][:8]} | {r['verdict']:14} | cand={str(r['candidate_produced']):5} | plaus={str(r['plausible_reproduced']):5} | is_infra={str(r['is_infra_error']):5} | persist_err={bool(r['persist_error'])}")

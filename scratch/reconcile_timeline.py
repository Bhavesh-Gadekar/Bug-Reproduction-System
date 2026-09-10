import subprocess
import json
import re
from datetime import datetime

# Fetch worker logs for run 3291ad5e
proc = subprocess.run(
    ["docker", "logs", "bug_reproduction_worker", "--since", "2026-09-10T06:19:40Z", "--until", "2026-09-10T06:22:30Z"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

lines = proc.stdout.splitlines() + proc.stderr.splitlines()

events = []
for line in lines:
    if "3291ad5e-e5f9-43be-ae61-baebd9cb7087" not in line:
        continue
    # Extract timestamp
    m_ts = re.match(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2},\d{3})", line)
    if m_ts:
        ts_str = m_ts.group(1)
        events.append((ts_str, line))

out = [f"Total events found: {len(events)}"]
for ts, l in events:
    safe_l = l.encode("ascii", "replace").decode("ascii")
    if "worker.graph:" in safe_l:
        part = safe_l.split("worker.graph:")[1].strip()
        try:
            d = json.loads(part)
            ev = d.get("event")
            node = d.get("node")
            dur = d.get("duration_ms", "")
            out.append(f"[{ts}] GRAPH: {ev} node={node} duration={dur}ms")
        except Exception:
            out.append(f"[{ts}] {safe_l[:120]}")
    elif "app.db: Logged run_step" in safe_l:
        m_step = re.search(r"node=(\w+).*?latency=(\d+)ms", safe_l)
        if m_step:
            out.append(f"[{ts}] DB STEP LOGGED: node={m_step.group(1)} inner_latency={m_step.group(2)}ms")
    elif "app.db: Recorded artifact" in safe_l or "persist: Uploaded artifact" in safe_l or "persist: Persisted run" in safe_l:
        out.append(f"[{ts}] DB/B2: {safe_l[24:120]}")
    elif "arq.worker:" in safe_l or "worker: InFlightTracker" in safe_l or "worker: Processing" in safe_l:
        out.append(f"[{ts}] WORKER: {safe_l[24:120]}")

with open("scratch/timeline_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("Wrote scratch/timeline_output.txt successfully")

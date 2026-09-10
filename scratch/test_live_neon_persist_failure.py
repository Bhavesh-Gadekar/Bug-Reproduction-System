import os
import sys
sys.path.insert(0, "/app")
import asyncio
import json
from pathlib import Path
from app.graph.state import BugReportState, RepoMeta, ExecutionRecord
from app.graph.nodes.persist import persist_node
from app.core.config import get_worker_settings

async def main():
    settings = get_worker_settings()
    # Point NEON_DATABASE_URL to an unreachable host to trigger real network failure
    settings.NEON_DATABASE_URL = "postgresql://neondb_owner:fake_pass@nonexistent-neon-midrun.test:5432/neondb"
    
    state = BugReportState(
        bug_report_id="9a8ab72c-ea6a-458f-a838-98278183be16",
        workspace_id="170258cb-09c3-426b-88b9-450f37c569ff",
        run_id="dead-letter-live-run-1234",
        title="Live Neon Failure Test",
        description="Testing live Neon unreachability in persist_node",
        raw_stack_trace="Traceback: AttributeError",
        repo=RepoMeta(git_url="https://github.com/tqdm/tqdm"),
        current_script="print('repro')",
        reproduced=False,
        execution_history=[]
    )

    print("Executing persist_node with unreachable Neon database URL...")
    result = await persist_node(state)
    print("=== RESULT RETURNED FROM persist_node ===")
    print(json.dumps(result, indent=2))

    dead_letter_file = Path("/tmp/dead_letter_runs/dead-letter-live-run-1234.json")
    if dead_letter_file.exists():
        print("\n=== DEAD LETTER FILE WRITTEN TO DISK ===")
        print(dead_letter_file.read_text(encoding="utf-8"))
    else:
        print("\nDead letter file not found!")

if __name__ == "__main__":
    asyncio.run(main())

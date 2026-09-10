import os
import sys
sys.path.insert(0, "/app")
import json
from app.graph.state import BugReportState, RepoMeta, ExecutionRecord
from app.graph.nodes.persist import _upload_b2_artifacts
from app.core.config import get_worker_settings

state = BugReportState(
    bug_report_id="9a8ab72c-ea6a-458f-a838-98278183be16",
    workspace_id="170258cb-09c3-426b-88b9-450f37c569ff",
    run_id="11a88139-3739-4da5-b473-5f541edb99e9",
    title="Live B2 Failure Test",
    description="Testing B2 live failure recording",
    raw_stack_trace="Traceback: AttributeError",
    repo=RepoMeta(git_url="https://github.com/tqdm/tqdm"),
    current_script="print('live test B2 failure')",
    execution_history=[]
)

settings = get_worker_settings()
print(f"Using B2_KEY_ID: {settings.B2_KEY_ID}")
print(f"Using B2_ENDPOINT: {settings.B2_ENDPOINT}")
summaries = _upload_b2_artifacts(state, settings)
print("=== LIVE SUMMARIES RETURNED ===")
print(json.dumps(summaries, indent=2))

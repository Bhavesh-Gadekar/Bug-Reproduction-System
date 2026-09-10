"""Test live stale fallback endpoint via ORM models."""

import uuid
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()
from app.db.session import get_engine
from app.models.bug_report import BugReport
from app.models.enums import ReproductionRunStatus
from app.models.reproduction import ReproductionRun, RunStep
from app.models.repo import Repo
from app.models.workspace import Workspace

engine = get_engine()
run_id = uuid.uuid4()
bug_report_id = uuid.uuid4()
workspace_id = uuid.uuid4()
repo_id = uuid.uuid4()
old_time = datetime.now(tz=timezone.utc) - timedelta(minutes=15)

with Session(engine) as session:
    ws = Workspace(id=workspace_id, name="Stale Test WS")
    repo = Repo(id=repo_id, workspace_id=workspace_id, git_url="https://github.com/test/repo")
    bug = BugReport(id=bug_report_id, workspace_id=workspace_id, repo_id=repo_id, title="Stale Bug Report")
    run = ReproductionRun(id=run_id, bug_report_id=bug_report_id, status=ReproductionRunStatus.ANALYZING, started_at=old_time)
    step = RunStep(id=uuid.uuid4(), run_id=run_id, node_name="repo_analysis", created_at=old_time)
    session.add_all([ws, repo, bug, run, step])
    session.commit()

print(f"Created stale test run {run_id} (inactive for 15 minutes in 'analyzing' state)")

# Query API with default 300s threshold
res = requests.get(f"http://localhost:8000/api/runs/{run_id}").json()
print("\n--- GET /api/runs/{run_id} (default threshold: 300s) ---")
print(f"status:       {res.get('status')}")
print(f"raw_status:   {res.get('raw_status')}")
print(f"is_stale:     {res.get('is_stale')}")
print(f"stale_reason: {res.get('stale_reason')}")

# Query API with 1800s threshold (not stale)
res2 = requests.get(f"http://localhost:8000/api/runs/{run_id}?stale_threshold_seconds=1800").json()
print("\n--- GET /api/runs/{run_id}?stale_threshold_seconds=1800 ---")
print(f"status:       {res2.get('status')}")
print(f"raw_status:   {res2.get('raw_status')}")
print(f"is_stale:     {res2.get('is_stale')}")
print(f"stale_reason: {res2.get('stale_reason')}")

with Session(engine) as session:
    session.delete(session.get(Workspace, workspace_id))
    session.commit()
print("\nCleaned up test entities.")

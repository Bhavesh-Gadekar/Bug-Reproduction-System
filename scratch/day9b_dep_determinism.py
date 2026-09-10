"""
Re-run the dependency_install step twice against identical pinned SHAs
for dateutil and jinja2 by directly invoking the node function.

We do this by constructing minimal BugReportState objects and calling
dependency_install_node directly, then comparing output.

Each call clones fresh (new UUID path) and installs deps, so if the
resolved version differs between call 1 and call 2, it's a real bug.
"""
from __future__ import annotations
import asyncio
import sys
import os
import uuid
from pathlib import Path

# Load .env
env_path = Path(".env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip().strip("'\"")

# Add worker to path
sys.path.insert(0, str(Path("worker").resolve()))

from app.graph.state import BugReportState, RepoConfig
from app.graph.nodes.repo_analysis import repo_analysis_node
from app.graph.nodes.dependency_install import dependency_install_node


async def run_one(fixture_name: str, git_url: str, commit_sha: str, run_num: int) -> dict:
    """Clone the repo and install deps, return the install output."""
    run_id = str(uuid.uuid4())
    state = BugReportState(
        bug_report_id=run_id,
        run_id=run_id,
        title=f"{fixture_name} dep-install test run {run_num}",
        raw_stack_trace="placeholder",
        repo=RepoConfig(
            git_url=git_url,
            base_commit_sha=commit_sha,
            branch="main",
        ),
    )

    print(f"\n{'='*60}")
    print(f"  {fixture_name.upper()} — RUN {run_num}  (run_id={run_id[:8]})")
    print(f"{'='*60}")

    # Clone
    print(f"  [1/2] repo_analysis: cloning {git_url} @ {commit_sha[:12]}...")
    repo_out = await repo_analysis_node(state)
    for k, v in repo_out.items():
        object.__setattr__(state, k, v)
    print(f"  actual_commit_sha: {repo_out.get('actual_commit_sha', 'N/A')}")
    print(f"  local_path: {repo_out.get('local_path', 'N/A')}")

    # Install
    print(f"  [2/2] dependency_install: running pip install...")
    dep_out = await dependency_install_node(state)

    # Extract the key lines
    install_output = dep_out.get("dependency_install_output", {})
    stdout = install_output.get("stdout", "")
    stderr = install_output.get("stderr", "")
    exit_code = install_output.get("exit_code", "N/A")

    # Find the "Successfully installed" line
    installed_line = next(
        (line for line in stdout.splitlines() if "Successfully installed" in line),
        "(not found in stdout)"
    )

    print(f"  exit_code:          {exit_code}")
    print(f"  Successfully installed: {installed_line}")

    return {
        "fixture": fixture_name,
        "run_num": run_num,
        "run_id": run_id,
        "actual_commit_sha": repo_out.get("actual_commit_sha"),
        "installed": installed_line.strip(),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }


async def main():
    FIXTURES = [
        {
            "name": "dateutil",
            "git_url": "https://github.com/dateutil/dateutil.git",
            "commit_sha": "fc9b1625ebc729f01e449879b6b140abd12ae621",
        },
        {
            "name": "jinja2",
            "git_url": "https://github.com/pallets/jinja.git",
            "commit_sha": "6478c22f29bb85b2bae635602148d95df5e5c7ce",
        },
    ]

    results_by_fixture = {}

    for fixture in FIXTURES:
        run1 = await run_one(fixture["name"], fixture["git_url"], fixture["commit_sha"], run_num=1)
        run2 = await run_one(fixture["name"], fixture["git_url"], fixture["commit_sha"], run_num=2)
        results_by_fixture[fixture["name"]] = (run1, run2)

    # Side-by-side comparison
    print("\n\n" + "="*70)
    print("  SIDE-BY-SIDE COMPARISON")
    print("="*70)
    for fixture_name, (r1, r2) in results_by_fixture.items():
        print(f"\n--- {fixture_name.upper()} ---")
        print(f"  Run 1 actual_sha:   {r1['actual_commit_sha']}")
        print(f"  Run 2 actual_sha:   {r2['actual_commit_sha']}")
        print(f"  Run 1 installed:    {r1['installed']}")
        print(f"  Run 2 installed:    {r2['installed']}")
        match = r1['installed'] == r2['installed']
        print(f"  DETERMINISTIC:      {'YES ✓' if match else 'NO — MISMATCH ✗'}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())

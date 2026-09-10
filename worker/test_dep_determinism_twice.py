"""
Determinism test: Re-run dependency-install step twice in a row against identical pinned commit SHAs
for dateutil and jinja2 inside the worker environment using full clone matching repo_analysis.
"""
from __future__ import annotations
import subprocess
import sys
import shutil
from pathlib import Path

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

def run_fixture(name: str, git_url: str, commit_sha: str, iteration: int) -> dict:
    target_dir = Path(f"/tmp/dep_test_{name}_iter{iteration}")
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n[{name.upper()} ITERATION {iteration}] Cloning {git_url}...", flush=True)
    subprocess.run(["git", "clone", git_url, str(target_dir)], check=True, capture_output=True)
    print(f"[{name.upper()} ITERATION {iteration}] Checking out {commit_sha[:10]}...", flush=True)
    subprocess.run(["git", "-C", str(target_dir), "checkout", commit_sha], check=True, capture_output=True)

    deps_dir = target_dir / ".deps"
    deps_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--prefer-binary",
        "--target", str(deps_dir),
        str(target_dir),
    ]
    cmd_str = " ".join(cmd)
    print(f"[{name.upper()} ITERATION {iteration}] Executing: {cmd_str}", flush=True)

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(target_dir),
        env={"PIP_DISABLE_PIP_VERSION_CHECK": "1", "PATH": sys.path[0]}
    )

    # Inspect installed dist-info / packages
    dist_infos = list(deps_dir.glob("*.dist-info"))
    installed_versions = [d.name.replace(".dist-info", "") for d in dist_infos]

    return {
        "iteration": iteration,
        "command": cmd_str,
        "exit_code": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "dist_infos": installed_versions,
    }

def main():
    results = {}
    for fix in FIXTURES:
        name = fix["name"]
        print(f"\n==================== TESTING {name.upper()} ====================", flush=True)
        res1 = run_fixture(name, fix["git_url"], fix["commit_sha"], 1)
        res2 = run_fixture(name, fix["git_url"], fix["commit_sha"], 2)
        results[name] = (res1, res2)

    print("\n\n" + "="*80, flush=True)
    print("                      SIDE-BY-SIDE RAW OUTPUT COMPARISON", flush=True)
    print("="*80, flush=True)

    for name, (r1, r2) in results.items():
        print(f"\n############################# {name.upper()} #############################", flush=True)
        print(f"--- RUN 1 (Exit Code: {r1['exit_code']}) ---", flush=True)
        print(f"Dist-info packages: {r1['dist_infos']}", flush=True)
        print("STDOUT:", flush=True)
        print(r1['stdout'].strip() or "(empty)", flush=True)
        if r1['stderr'].strip():
            print("STDERR:", flush=True)
            print(r1['stderr'].strip(), flush=True)

        print(f"\n--- RUN 2 (Exit Code: {r2['exit_code']}) ---", flush=True)
        print(f"Dist-info packages: {r2['dist_infos']}", flush=True)
        print("STDOUT:", flush=True)
        print(r2['stdout'].strip() or "(empty)", flush=True)
        if r2['stderr'].strip():
            print("STDERR:", flush=True)
            print(r2['stderr'].strip(), flush=True)

        print("\n--- COMPARISON ---", flush=True)
        print(f"Run 1 Installed: {sorted(r1['dist_infos'])}", flush=True)
        print(f"Run 2 Installed: {sorted(r2['dist_infos'])}", flush=True)
        match = (sorted(r1['dist_infos']) == sorted(r2['dist_infos'])) and (r1['exit_code'] == r2['exit_code'])
        print(f"Determinism Check: {'MATCH (Deterministic) ✓' if match else 'MISMATCH (Non-deterministic) ✗'}", flush=True)
        print("="*80, flush=True)

if __name__ == "__main__":
    main()

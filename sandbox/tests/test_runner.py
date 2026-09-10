"""Integration tests for the sandbox runner.

These tests require:
  - A live Docker daemon reachable via the Docker CLI (``docker`` in PATH)
  - The ``python:3.11-slim`` image available locally or pullable from the registry

All tests are marked ``@pytest.mark.integration`` so they can be excluded
from fast unit-only CI runs:

    pytest tests/ -m "not integration"   # skip these
    pytest tests/ -m integration -v      # run only these

On Windows they must be executed inside WSL2 or via:
    docker compose run --rm sandbox pytest tests/ -m integration -v
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.runner import JobRequest, JobResult, run_job

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

FIXTURE_REPO_PATH = Path(__file__).parent / "fixture_repo"
"""Absolute path to the deliberately-failing pytest project."""

BASE_IMAGE = "python:3.11-slim"
"""Image used for all tests — must be pullable or already present."""

FIXTURE_IMAGE = "sandbox-fixture-runner:latest"
"""
A local throw-away image that extends python:3.11-slim with pytest pre-installed.
Built once per test session in the ``fixture_image`` fixture (uses normal network
access during `docker build`).  The sandboxed containers that run the actual test
therefore never need outbound network access, even with --network=none.
"""


def _default_settings(**overrides) -> Settings:
    """Return a Settings object, bypassing .env loading for test isolation."""
    defaults = {
        "ENVIRONMENT": "test",
        "DEFAULT_CPU_LIMIT": 0.5,
        "DEFAULT_MEMORY_LIMIT": "256m",
        "DEFAULT_PIDS_LIMIT": 64,
        "MAX_TIMEOUT_SECONDS": 120,
        "WATCHDOG_GRACE_SECONDS": 5,
        "SANDBOX_NETWORK": "none",
        "ALLOW_IMAGE_PULL": True,
    }
    defaults.update(overrides)
    # Construct directly, bypassing env-file loading
    return Settings.model_construct(**defaults)


@pytest.fixture(scope="session", autouse=True)
def ensure_docker_available():
    """
    Session-scoped fixture: verify ``docker info`` succeeds before any test
    runs.  Skips the entire session if Docker is not reachable.
    """
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        timeout=15,
    )
    if result.returncode != 0:
        pytest.skip("Docker daemon is not available — skipping all integration tests")


@pytest.fixture(scope="session", autouse=True)
def fixture_image(ensure_docker_available):
    """
    Build a local image with pytest and the fixture tests baked in.

    We use FIXTURE_REPO_PATH as the ``docker build`` context and COPY it into
    the image at ``/fixture_repo``.  This avoids any bind-mount path issues
    when running under Docker-out-of-Docker: the DooD daemon resolves volume
    source paths on the HOST, not inside the sandbox container, so a path like
    ``/app/tests/fixture_repo`` (valid inside the container) would not exist on
    the host.  Baking the files into the image sidesteps the problem entirely.

    The build uses normal host network access; only the subsequent ``docker run``
    uses ``--network=none``.
    """
    dockerfile = (
        f"FROM {BASE_IMAGE}\n"
        "RUN pip install --no-cache-dir pytest\n"
        # COPY . copies the build context (FIXTURE_REPO_PATH) into /fixture_repo
        "COPY . /fixture_repo\n"
    )
    result = subprocess.run(
        # Pass FIXTURE_REPO_PATH as the build context so COPY . works
        ["docker", "build", "--tag", FIXTURE_IMAGE, "--file", "-", str(FIXTURE_REPO_PATH)],
        input=dockerfile.encode(),
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        pytest.skip(
            f"Could not build fixture image: {result.stderr.decode()[:500]}"
        )
    yield FIXTURE_IMAGE
    # Teardown: remove the local image to keep the daemon clean
    subprocess.run(
        ["docker", "rmi", "--force", FIXTURE_IMAGE],
        capture_output=True,
        timeout=15,
    )


@pytest.fixture(scope="session")
def settings() -> Settings:
    return _default_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — Failing test capture
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_failing_pytest_captured(settings: Settings, fixture_image: str):
    """
    Runs pytest against the fixture test suite baked into ``fixture_image``.
    pytest is pre-installed and the tests live at ``/fixture_repo/tests``
    inside the image, so the container needs neither network access nor a
    bind mount (both of which are problematic under Docker-out-of-Docker).

    ``-p no:cacheprovider`` suppresses pytest's attempt to write
    ``.pytest_cache`` to the read-only root filesystem.

    Assertions:
      - exit_code != 0  (pytest exits 1 when >=1 test fails)
      - "FAILED" appears in stdout
      - "test_always_fails" appears in stdout
      - "passed" appears in stdout  (the always-passing companion test ran)
      - timed_out is False
    """
    result = _run_direct(
        image=fixture_image,
        # /fixture_repo/tests is baked into the image by the session fixture
        # -p no:cacheprovider: don't write .pytest_cache on the read-only rootfs
        command=["pytest", "/fixture_repo/tests", "-v", "-p", "no:cacheprovider"],
        timeout=60,
        settings=settings,
    )

    assert result.exit_code != 0, (
        f"Expected non-zero exit code from failing pytest, got {result.exit_code}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "FAILED" in result.stdout, (
        f"Expected 'FAILED' in pytest stdout.\nstdout:\n{result.stdout}"
    )
    assert "test_always_fails" in result.stdout, (
        "Expected 'test_always_fails' to appear in pytest output"
    )
    assert "passed" in result.stdout, (
        "Expected at least one passed test in pytest output"
    )
    assert not result.timed_out, "Test should not have timed out"


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — Fork-bomb killed by PID limit
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_fork_bomb_killed_by_pid_limit(settings: Settings):
    """
    A Python os.fork() loop tries to spawn 500 child processes.  With
    --pids-limit=32 the kernel returns EAGAIN after ~25 forks; the script
    catches the resulting OSError and exits with code 1.

    We use Python (not a bash fork-bomb) because the bash one exits 0:
    the parent shell finishes normally even as all the child forks get
    killed by the PID cap, so the container's exit code is 0.
    Python's os.fork() raises an OSError that we explicitly propagate as
    a non-zero exit, making the assertion reliable.

    Assertions:
      - exit_code != 0  (OSError hit, script calls sys.exit(1))
      - Wall-clock time well under deadline (PID cap triggers fast)
      - timed_out is False
    """
    pids_limit = 32  # tight cap — leaves ~25 slots for child processes
    fork_bomb_settings = _default_settings(DEFAULT_PIDS_LIMIT=pids_limit)

    # Script: fork in a loop until the kernel refuses; exit non-zero when it does.
    # If somehow 500 forks succeed (limit not enforced) exit 2 so we still fail.
    pid_limit_script = (
        "import os, sys\n"
        "created = []\n"
        "for i in range(500):\n"
        "    try:\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        "            import time; time.sleep(60)\n"
        "        else:\n"
        "            created.append(pid)\n"
        "    except OSError as e:\n"
        "        print(f'PID limit hit after {len(created)} forks: {e}', flush=True)\n"
        "        sys.exit(1)\n"
        "# Should never reach here with --pids-limit=32\n"
        "print(f'ERROR: spawned {len(created)} without hitting limit', flush=True)\n"
        "sys.exit(2)\n"
    )

    deadline = 30
    start = time.monotonic()

    result = _run_direct(
        image=BASE_IMAGE,
        command=["python3", "-c", pid_limit_script],
        timeout=deadline,
        settings=fork_bomb_settings,
    )

    elapsed = time.monotonic() - start

    assert result.exit_code != 0, (
        "Expected non-zero exit when PID limit is hit, "
        f"but got exit_code={result.exit_code}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert elapsed < deadline, (
        f"PID-limit test took {elapsed:.1f}s — expected it to finish well before {deadline}s"
    )
    assert not result.timed_out, (
        "Container should be killed by PID limit, not by our timeout"
    )
    # Confirm the PID limit was actually the cause (not some other error)
    assert "PID limit hit" in result.stdout, (
        f"Expected 'PID limit hit' in stdout.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 2b — Timeout enforcement
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_timeout_enforcement(settings: Settings):
    """
    A process that runs longer than timeout_seconds must be terminated by the runner,
    returning timed_out=True within a reasonable bound.
    """
    request = JobRequest(
        base_image=BASE_IMAGE,
        command=["python3", "-c", "import time; time.sleep(30)"],
        timeout_seconds=2,
    )
    start = time.monotonic()
    result = run_job(request, settings)
    elapsed = time.monotonic() - start

    assert result.timed_out is True, "Expected job to be marked timed_out"
    assert elapsed < 10, f"Expected timeout enforcement within 10s, took {elapsed:.1f}s"



# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — Network isolation (--network=none)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_network_isolation(settings: Settings):
    """
    With --network=none any outbound TCP connection attempt must fail.
    We use Python's urllib (always present in python:3.11-slim) to attempt
    a connection to 1.1.1.1:443 and assert it raises an exception.

    Assertions:
      - exit_code != 0  (the Python script exits with sys.exit(1))
      - stdout or stderr contains a network error keyword
    """
    network_test_script = (
        "import socket, sys\n"
        "try:\n"
        "    s = socket.create_connection(('1.1.1.1', 443), timeout=5)\n"
        "    s.close()\n"
        "    print('NETWORK_REACHABLE')\n"
        "    sys.exit(0)\n"
        "except OSError as e:\n"
        "    print(f'NETWORK_BLOCKED: {e}')\n"
        "    sys.exit(1)\n"
    )

    result = _run_direct(
        image=BASE_IMAGE,
        command=["python", "-c", network_test_script],
        timeout=15,
        settings=settings,  # SANDBOX_NETWORK="none"
    )

    assert result.exit_code != 0, (
        "Expected network connection to fail inside --network=none container, "
        f"but exit_code={result.exit_code}.\nstdout: {result.stdout}"
    )
    combined = result.stdout + result.stderr
    assert "NETWORK_REACHABLE" not in combined, (
        "Container had unexpected network access despite --network=none"
    )
    # The error will be something like "Network is unreachable" or
    # "Connection refused" or "Name or service not known"
    assert any(
        kw in combined
        for kw in ("NETWORK_BLOCKED", "unreachable", "refused", "not known", "blocked")
    ), f"Expected a network error message, got:\n{combined}"


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers — thin wrappers around docker run
# ──────────────────────────────────────────────────────────────────────────────


def _build_security_flags(settings: Settings) -> list[str]:
    """Return the common security/resource docker run flags."""
    return [
        f"--network={settings.SANDBOX_NETWORK}",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--cpus={settings.DEFAULT_CPU_LIMIT}",
        f"--memory={settings.DEFAULT_MEMORY_LIMIT}",
        f"--pids-limit={settings.DEFAULT_PIDS_LIMIT}",
    ]


def _run_direct(
    image: str,
    command: list[str],
    timeout: int,
    settings: Settings,
) -> JobResult:
    """
    Thin helper that builds a ``docker run`` invocation with the full
    security profile and returns a :class:`JobResult`.  Used for tests
    that don't need a bind mount.
    """
    from app.runner import JobResult

    import uuid

    container_name = f"sandbox-test-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        *_build_security_flags(settings),
        image,
        *command,
    ]
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)
        stdout, stderr, exit_code = "", "TIMEOUT", -1
    duration = time.monotonic() - start

    return JobResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_seconds=round(duration, 3),
        timed_out=timed_out,
        container_id=container_name,
    )


def _run_with_mount(
    image: str,
    mount_src: str,
    mount_dst: str,
    command: list[str],
    timeout: int,
    settings: Settings,
) -> JobResult:
    """
    Like ``_run_direct`` but adds a read-only bind mount.

    Note: bind mounts conflict with ``--read-only`` only for the *container*
    filesystem — the bind-mounted volume itself is not affected by the
    read-only flag.
    """
    from app.runner import JobResult

    import uuid

    container_name = f"sandbox-test-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--volume", f"{mount_src}:{mount_dst}:ro",
        *_build_security_flags(settings),
        image,
        *command,
    ]
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)
        stdout, stderr, exit_code = "", "TIMEOUT", -1
    duration = time.monotonic() - start

    return JobResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_seconds=round(duration, 3),
        timed_out=timed_out,
        container_id=container_name,
    )

"""Core container execution logic for the sandbox runner.

Each call to `run_job()` does the following:
1. (Optional) Pull the image if it is not present locally.
2. Start a Docker container via `docker run` with the full security profile.
3. Spawn a watchdog thread that hard-kills the container at
   ``timeout + WATCHDOG_GRACE_SECONDS`` in case the primary subprocess
   timeout is not honoured (e.g. the process is blocked in a syscall).
4. Collect stdout / stderr, exit code, and wall-clock duration, then
   remove the container.

Design note: We deliberately use ``subprocess`` + the Docker CLI rather
than the ``docker`` Python SDK so that the service has zero heavyweight
dependencies and can stream output in a future iteration without changes
to this module's interface.
"""

import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field

from app.config import Settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class JobRequest:
    """Inputs for a single sandboxed execution."""

    base_image: str
    command: list[str]
    timeout_seconds: int
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResult:
    """Outputs returned to the caller after execution completes."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool
    container_id: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _pull_image(image: str) -> None:
    """Pull *image* from the registry; log but do not raise on failure."""
    logger.info("Pulling image: %s", image)
    result = subprocess.run(
        ["docker", "pull", image],
        capture_output=True,
        text=True,
        timeout=300,  # 5-minute pull timeout
    )
    if result.returncode != 0:
        logger.warning("docker pull failed for %s: %s", image, result.stderr.strip())


def _force_kill(container_name: str, fired: threading.Event) -> None:
    """
    Watchdog target: attempt ``docker kill`` then ``docker rm -f`` and
    record that the container was force-killed by setting *fired*.
    """
    logger.warning("Watchdog: force-killing container %s", container_name)
    subprocess.run(
        ["docker", "kill", container_name],
        capture_output=True,
        timeout=10,
    )
    fired.set()


def _remove_container(container_name: str) -> None:
    """Best-effort container removal — errors are logged and swallowed."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not remove container %s: %s", container_name, exc)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def run_job(request: JobRequest, settings: Settings) -> JobResult:
    """
    Execute *request* inside a Docker container with the full security
    profile defined in *settings* and return a :class:`JobResult`.

    This function is **synchronous** and is intended to be called from
    a FastAPI endpoint via ``asyncio.get_event_loop().run_in_executor``.
    """
    # ── 0. Validate timeout ───────────────────────────────────────────────────
    timeout = min(request.timeout_seconds, settings.MAX_TIMEOUT_SECONDS)
    watchdog_deadline = timeout + settings.WATCHDOG_GRACE_SECONDS

    # ── 1. Optional image pull ────────────────────────────────────────────────
    if settings.ALLOW_IMAGE_PULL:
        # Check whether the image exists locally first to avoid unnecessary
        # registry round-trips on every call.
        inspect = subprocess.run(
            ["docker", "image", "inspect", request.base_image],
            capture_output=True,
        )
        if inspect.returncode != 0:
            _pull_image(request.base_image)

    # ── 2. Build the docker run command ──────────────────────────────────────
    container_name = f"sandbox-{uuid.uuid4().hex[:12]}"

    cmd: list[str] = [
        "docker",
        "run",
        "--rm",  # auto-remove on exit (belt + suspenders with explicit rm)
        "--name",
        container_name,
        # ── Network isolation ─────────────────────────────────────────────────
        f"--network={settings.SANDBOX_NETWORK}",
        # ── Filesystem security ───────────────────────────────────────────────
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        # ── Linux capability hardening ────────────────────────────────────────
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        # ── Resource limits ───────────────────────────────────────────────────
        f"--cpus={settings.DEFAULT_CPU_LIMIT}",
        f"--memory={settings.DEFAULT_MEMORY_LIMIT}",
        f"--pids-limit={settings.DEFAULT_PIDS_LIMIT}",
    ]

    # Inject extra environment variables requested by the caller
    for key, value in request.env.items():
        cmd += ["--env", f"{key}={value}"]

    cmd.append(request.base_image)
    cmd.extend(request.command)

    logger.info(
        "Launching container %s | image=%s | timeout=%ds",
        container_name,
        request.base_image,
        timeout,
    )

    # ── 3. Start the container ────────────────────────────────────────────────
    timed_out = False
    watchdog_fired = threading.Event()
    watchdog: threading.Timer | None = None
    start_time = time.monotonic()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # ── 4. Arm the watchdog ───────────────────────────────────────────────
        # The watchdog fires at timeout + WATCHDOG_GRACE_SECONDS.  It runs
        # _force_kill in a daemon thread so it does not block on join().
        watchdog = threading.Timer(
            watchdog_deadline,
            _force_kill,
            args=(container_name, watchdog_fired),
        )
        watchdog.daemon = True
        watchdog.start()

        # ── 5. Wait for completion ────────────────────────────────────────────
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            # Primary timeout expired; send SIGKILL via docker kill and drain
            logger.warning("Primary timeout expired for container %s", container_name)
            subprocess.run(
                ["docker", "kill", container_name],
                capture_output=True,
                timeout=10,
            )
            stdout, stderr = proc.communicate()
            exit_code = proc.returncode

    finally:
        # Cancel watchdog if still pending
        if watchdog is not None:
            watchdog.cancel()
        # Mark timed_out=True if the watchdog fired independently
        if watchdog_fired.is_set():
            timed_out = True
        # Best-effort cleanup — the container may already be gone (--rm)
        _remove_container(container_name)

    duration = time.monotonic() - start_time

    logger.info(
        "Container %s finished | exit_code=%d | duration=%.2fs | timed_out=%s",
        container_name,
        exit_code,
        duration,
        timed_out,
    )

    return JobResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_seconds=round(duration, 3),
        timed_out=timed_out,
        container_id=container_name,
    )

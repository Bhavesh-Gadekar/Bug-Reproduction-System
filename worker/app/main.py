"""Main entrypoint and Arq worker for Bug Reproduction System."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import logging
import sys
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from arq.connections import RedisSettings
from arq.worker import run_worker

from app.core.config import get_worker_settings
from app.db import get_checkpointer
from app.graph.graph import make_graph
from app.graph.sandbox import RealSandboxClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

settings = get_worker_settings()


class ReproductionWorker:
    """Manages LangGraph pipeline lifecycle and processes reproduction jobs."""

    def __init__(self):
        self.is_running = False
        self.settings = settings
        self.sandbox_client = RealSandboxClient(self.settings.SANDBOX_URL)
        self.graph: Any = None
        self._checkpointer_ctx: Any = None
        self.checkpointer_type: str = "unknown"
        self.checkpointer_degraded: bool = False
        self._reconciliation_task: asyncio.Task | None = None

    async def _probe_sandbox(self) -> bool:
        """Health-check the sandbox service. Returns True if reachable, False otherwise."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.settings.SANDBOX_URL}/health")
                return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sandbox health probe failed: %s", exc)
            return False

    async def start_dependencies(self):
        """Initialize LLM, sandbox client, database checkpointer, and compile LangGraph."""
        logger.info("Initializing %s dependencies...", self.settings.SERVICE_NAME)
        logger.info(
            "Config status: Gemini=%s, NeonDB=%s, BackblazeB2=%s, Sandbox=%s",
            bool(self.settings.GEMINI_API_KEY),
            bool(self.settings.NEON_DATABASE_URL),
            bool(self.settings.B2_KEY_ID and self.settings.B2_APPLICATION_KEY),
            self.settings.SANDBOX_URL,
        )

        # ── Sandbox health check ── must be explicit, never silent ────────────
        sandbox_reachable = await self._probe_sandbox()
        logger.info(
            "SANDBOX_CLIENT_TYPE=RealSandboxClient url=%s reachable=%s",
            self.settings.SANDBOX_URL,
            sandbox_reachable,
        )
        if not sandbox_reachable:
            raise RuntimeError(
                f"STARTUP FAILURE: RealSandboxClient at {self.settings.SANDBOX_URL} is not reachable. "
                "Ensure the sandbox service is up before starting the worker. "
                "Set SANDBOX_URL to an accessible endpoint or check docker-compose sandbox service."
            )

        # ── Checkpointer setup ── fail-fast when Neon is configured but unreachable
        checkpointer = None
        self.checkpointer_type = "MemorySaver"
        self.checkpointer_degraded = False

        if self.settings.NEON_DATABASE_URL:
            try:
                self._checkpointer_ctx = get_checkpointer()
                checkpointer = await self._checkpointer_ctx.__aenter__()
                self.checkpointer_type = "PostgresSaver"
                logger.info("CHECKPOINTER_TYPE=PostgresSaver (Neon connection pool enabled)")
            except Exception as exc:  # noqa: BLE001
                self.checkpointer_degraded = True
                self.checkpointer_type = "MemorySaver (degraded)"
                logger.error(
                    "CHECKPOINTER_TYPE=MemorySaver (degraded) - Failed to initialize Postgres checkpointer: %s",
                    exc,
                )
                if not getattr(self.settings, "ALLOW_DEGRADED_CHECKPOINTER", False):
                    raise RuntimeError(
                        f"STARTUP FAILURE: NEON_DATABASE_URL is configured but unreachable: {exc}. "
                        "Refusing to start with degraded MemorySaver. Set ALLOW_DEGRADED_CHECKPOINTER=true to override."
                    ) from exc
                from langgraph.checkpoint.memory import MemorySaver

                checkpointer = MemorySaver()
        else:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()
            self.checkpointer_type = "MemorySaver (offline)"
            logger.warning("CHECKPOINTER_TYPE=MemorySaver (offline) - NEON_DATABASE_URL not configured.")

        if self.settings.GEMINI_API_KEY:
            from app.graph.llm import GeminiLLMClient

            llm = GeminiLLMClient()
            logger.info("Initialized GeminiLLMClient with model=%s", llm.model)
        else:
            from app.graph.llm import FakeLLMClient

            llm = FakeLLMClient()
            logger.warning("GEMINI_API_KEY not configured. Falling back to FakeLLMClient.")

        # Exactly reuse the production make_graph assembly
        self.graph = make_graph(
            llm=llm,
            sandbox=self.sandbox_client,
            checkpointer=checkpointer,
            timeout_seconds=self.settings.SANDBOX_TIMEOUT_SECONDS,
        )
        self.is_running = True
        logger.info("LangGraph reproduction state machine initialized successfully.")

        # Reconcile dead-letter runs on startup and start periodic background reconciliation
        try:
            from app.reconciliation import reconcile_dead_letter_runs

            await reconcile_dead_letter_runs(self.settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Initial dead-letter reconciliation failed: %s", exc)

        self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())

    async def process_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a reproduction task through the compiled LangGraph state machine."""
        if not self.graph:
            raise RuntimeError("Graph not initialized. Call start_dependencies() first.")

        bug_report_id = task_payload.get("bug_report_id", "default_thread")
        run_id = task_payload.get("run_id") or bug_report_id
        config = {"configurable": {"thread_id": str(bug_report_id)}}

        # Log system initialization telemetry to run_steps so checkpointer type is durable
        from app.db import log_run_step
        log_run_step(
            run_id=run_id,
            node_name="system_init",
            input_data={"bug_report_id": str(bug_report_id), "run_id": str(run_id)},
            output_data={
                "checkpointer_type": self.checkpointer_type,
                "checkpointer_degraded": self.checkpointer_degraded,
                "sandbox_client": "RealSandboxClient",
                "sandbox_url": self.settings.SANDBOX_URL,
                "gemini_model": self.settings.GEMINI_MODEL,
            },
            latency_ms=0,
        )

        task_payload["checkpointer_type"] = self.checkpointer_type
        task_payload["checkpointer_degraded"] = self.checkpointer_degraded

        logger.info(
            "Processing bug reproduction task for report %s (run_id: %s, checkpointer: %s)",
            bug_report_id,
            run_id,
            self.checkpointer_type,
        )
        result = await self.graph.ainvoke(task_payload, config=config)
        logger.info(
            "Task complete for %s. Verdict: %s (reproduced: %s)",
            bug_report_id,
            result.get("final_verdict"),
            result.get("reproduced"),
        )
        return result

    async def _reconciliation_loop(self, interval_seconds: int = 60):
        """Periodically scan for and reconcile dead-letter runs when Neon is restored."""
        from app.reconciliation import reconcile_dead_letter_runs

        while self.is_running:
            try:
                await asyncio.sleep(interval_seconds)
                if not self.is_running:
                    break
                await reconcile_dead_letter_runs(self.settings)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.debug("Background dead-letter reconciliation error: %s", exc)

    async def shutdown(self):
        """Clean up resources on worker termination."""
        logger.info("Shutting down %s...", self.settings.SERVICE_NAME)
        self.is_running = False
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconciliation_task
        if self._checkpointer_ctx:
            with contextlib.suppress(Exception):
                await self._checkpointer_ctx.__aexit__(None, None, None)
        await self.sandbox_client.aclose()


# ---------------------------------------------------------------------------
# Arq Job Functions & Lifecycle Hooks
# ---------------------------------------------------------------------------

class InFlightTracker:
    """Thread-safe tracker for in-flight reproduction run IDs and worker uptime."""

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self.active_runs: set[str] = set()
        self.started_at: datetime = datetime.now(timezone.utc)

    def start_run(self, run_id: str):
        with self._lock:
            self.active_runs.add(str(run_id))
            logger.info("InFlightTracker: started tracking run_id=%s (current in_flight: %s)", run_id, list(self.active_runs))

    def end_run(self, run_id: str):
        with self._lock:
            self.active_runs.discard(str(run_id))
            logger.info("InFlightTracker: ended tracking run_id=%s (remaining in_flight: %s)", run_id, list(self.active_runs))

    def get_in_flight(self) -> list[str]:
        with self._lock:
            return list(self.active_runs)


in_flight_tracker = InFlightTracker()


async def run_reproduction_task(ctx: dict[str, Any], task_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Arq job handler invoked when a reproduction task is consumed from Redis.
    Delegates task execution directly to the compiled LangGraph state machine.
    """
    worker: ReproductionWorker = ctx["worker"]
    run_id = task_payload.get("run_id") or task_payload.get("bug_report_id")
    if run_id:
        in_flight_tracker.start_run(str(run_id))
    try:
        return await worker.process_task(task_payload)
    finally:
        if run_id:
            in_flight_tracker.end_run(str(run_id))


async def startup(ctx: dict[str, Any]):
    """Arq worker startup hook."""
    import os
    import traceback
    from app.db import record_worker_incident

    logger.info("Starting Arq worker for queue: %s", settings.TASK_QUEUE_NAME)
    in_flight_tracker.started_at = datetime.now(timezone.utc)
    worker = ReproductionWorker()
    await worker.start_dependencies()
    ctx["worker"] = worker

    redis_pool = ctx.get("redis")
    if redis_pool and hasattr(redis_pool, "connection_pool"):
        redis_pool.connection_pool.connection_kwargs["socket_timeout"] = 2.0

    # Install asyncio loop exception handler to trap orphan background tasks
    loop = asyncio.get_running_loop()
    _orig_loop_handler = loop.get_exception_handler()

    def _loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]):
        exc = context.get("exception")
        if exc is not None:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            logger.critical("FATAL: Unhandled exception in worker event loop: %s\n%s", exc, tb_str)
            record_worker_incident(
                exception=exc,
                tb_str=tb_str,
                in_flight_run_ids=in_flight_tracker.get_in_flight(),
                worker_started_at=in_flight_tracker.started_at,
            )
            # Fail loudly: exit non-zero so Docker restarts the container
            os._exit(1)
        if _orig_loop_handler:
            _orig_loop_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_loop_exception_handler)

    # Active broker liveness monitor to fail fast when Redis drops mid-flight
    async def _redis_watchdog():
        import redis.exceptions
        while True:
            await asyncio.sleep(2.0)
            if redis_pool:
                try:
                    await redis_pool.ping()
                except (redis.exceptions.RedisError, ConnectionError, OSError) as exc:
                    logger.critical("FATAL: Redis broker connectivity lost: %s", exc)
                    _handle_unhandled_crash(type(exc), exc, exc.__traceback__)
                    os._exit(1)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("Transient check error in _redis_watchdog: %s", exc)

    ctx["_redis_watchdog"] = asyncio.create_task(_redis_watchdog())


async def shutdown(ctx: dict[str, Any]):
    """Arq worker shutdown hook."""
    watchdog = ctx.get("_redis_watchdog")
    if watchdog:
        watchdog.cancel()
    worker: ReproductionWorker = ctx.get("worker")
    if worker:
        await worker.shutdown()


class WorkerSettings:
    """Arq worker configuration."""

    functions = [run_reproduction_task]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    queue_name = settings.TASK_QUEUE_NAME
    max_jobs = settings.WORKER_CONCURRENCY
    health_check_interval = 2
    on_startup = startup
    on_shutdown = shutdown



def _handle_unhandled_crash(exc_type: type[BaseException], exc_value: BaseException, exc_tb: Any):
    """Global crash handler writing an incident before process exit."""
    import traceback
    from app.db import record_worker_incident

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("FATAL: Unhandled exception in worker process: %s\n%s", exc_value, tb_str)
    record_worker_incident(
        exception=exc_value,
        tb_str=tb_str,
        in_flight_run_ids=in_flight_tracker.get_in_flight(),
        worker_started_at=in_flight_tracker.started_at,
    )


def start_worker_supervisor():
    """Run Arq worker under crash supervisor; fail loudly and record incident on any crash."""
    import sys
    import time
    import traceback
    import arq.connections
    import arq.worker

    # Ensure all Redis connections use a strict socket_timeout so dead sockets fail fast
    _orig_create_pool = arq.connections.create_pool

    async def _create_pool_with_timeout(*args, **kwargs):
        pool = await _orig_create_pool(*args, **kwargs)
        pool.connection_pool.connection_kwargs["socket_timeout"] = 2.0
        return pool

    arq.connections.create_pool = _create_pool_with_timeout
    arq.worker.create_pool = _create_pool_with_timeout

    # Install sys.excepthook as fallback
    _orig_excepthook = sys.excepthook

    def _excepthook_wrapper(exc_type, exc_value, exc_tb):
        _handle_unhandled_crash(exc_type, exc_value, exc_tb)
        _orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook_wrapper

    try:
        cur_settings = get_worker_settings()
        WorkerSettings.redis_settings = RedisSettings.from_dsn(cur_settings.REDIS_URL)
        WorkerSettings.redis_settings.conn_retries = 6
        WorkerSettings.redis_settings.conn_retry_delay = 5
        logger.info("Launching Arq reproduction worker listening on %s...", cur_settings.REDIS_URL)
        run_worker(WorkerSettings)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)) and getattr(exc, "code", 0) == 0:
            raise
        _handle_unhandled_crash(type(exc), exc, exc.__traceback__)
        # Backoff sleep before non-zero exit so Docker restart policy doesn't spin in a rapid crash loop
        time.sleep(15.0)
        raise


if __name__ == "__main__":
    start_worker_supervisor()

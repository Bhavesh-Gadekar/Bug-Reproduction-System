"""Main entrypoint and consumer loop for Bug Reproduction Worker."""

import asyncio
import contextlib
import logging
import signal
from typing import Any

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
    def __init__(self):
        self.is_running = False
        self.settings = settings
        self.sandbox_client = RealSandboxClient(self.settings.SANDBOX_URL)
        self.graph: Any = None

    async def initialize_graph(self, checkpointer: Any = None):
        """Build the LangGraph state machine with the provided checkpointer."""
        if self.settings.GEMINI_API_KEY:
            from app.graph.llm import GeminiLLMClient
            llm = GeminiLLMClient()
            logger.info("Initialized GeminiLLMClient with model=%s", llm.model)
        else:
            from app.graph.llm import FakeLLMClient
            llm = FakeLLMClient()
            logger.warning("GEMINI_API_KEY not configured. Falling back to FakeLLMClient.")

        self.graph = make_graph(
            llm=llm,
            sandbox=self.sandbox_client,
            checkpointer=checkpointer,
        )
        logger.info("LangGraph reproduction state machine initialized.")

    async def process_task(self, task_payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a reproduction task through the compiled LangGraph."""
        if not self.graph:
            raise RuntimeError("Graph not initialized")

        bug_report_id = task_payload.get("bug_report_id", "default_thread")
        config = {"configurable": {"thread_id": bug_report_id}}

        logger.info("Processing bug reproduction task for report %s", bug_report_id)
        result = await self.graph.ainvoke(task_payload, config=config)
        return result

    async def start(self):
        """Initialize worker connections and begin polling tasks."""
        self.is_running = True
        logger.info("Starting %s...", self.settings.SERVICE_NAME)
        logger.info("Connecting to Redis queue: %s", self.settings.TASK_QUEUE_NAME)
        logger.info(
            "Config status: Gemini=%s, NeonDB=%s, BackblazeB2=%s, Sandbox=%s",
            bool(self.settings.GEMINI_API_KEY),
            bool(self.settings.NEON_DATABASE_URL),
            bool(self.settings.B2_KEY_ID and self.settings.B2_APPLICATION_KEY),
            self.settings.SANDBOX_URL,
        )

        checkpointer_ctx = None
        if self.settings.NEON_DATABASE_URL:
            try:
                checkpointer_ctx = get_checkpointer()
                checkpointer = await checkpointer_ctx.__aenter__()
                logger.info("Postgres checkpointer enabled via Neon connection pool.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to initialize Postgres checkpointer: %s. Using in-memory checkpointer.", exc)
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
        else:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()

        await self.initialize_graph(checkpointer=checkpointer)

        try:
            while self.is_running:
                # Polling / task consumer loop (placeholder for Redis blpop)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("Worker task received cancellation.")
        finally:
            if checkpointer_ctx:
                with contextlib.suppress(Exception):
                    await checkpointer_ctx.__aexit__(None, None, None)
            await self.shutdown()

    async def shutdown(self):
        """Clean up resources on worker shutdown."""
        logger.info("Shutting down %s...", self.settings.SERVICE_NAME)
        self.is_running = False
        await self.sandbox_client.aclose()


async def main():
    worker = ReproductionWorker()

    loop = asyncio.get_running_loop()

    def handle_signal():
        worker.is_running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, handle_signal)

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())

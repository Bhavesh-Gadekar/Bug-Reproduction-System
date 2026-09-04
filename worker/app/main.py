import asyncio
import logging
import signal

from app.core.config import get_worker_settings

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

    async def start(self):
        """Initialize worker connections and begin polling tasks."""
        self.is_running = True
        logger.info("Starting %s...", self.settings.SERVICE_NAME)
        logger.info("Connecting to Redis queue: %s", self.settings.TASK_QUEUE_NAME)
        logger.info(
            "Config status: Gemini=%s, NeonDB=%s, BackblazeB2=%s",
            bool(self.settings.GEMINI_API_KEY),
            bool(self.settings.NEON_DATABASE_URL),
            bool(self.settings.B2_KEY_ID and self.settings.B2_APPLICATION_KEY),
        )

        try:
            while self.is_running:
                # Polling / task consumer loop (placeholder for LangGraph task execution)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            logger.info("Worker task received cancellation.")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean up resources on worker shutdown."""
        logger.info("Shutting down %s...", self.settings.SERVICE_NAME)
        self.is_running = False


async def main():
    worker = ReproductionWorker()

    loop = asyncio.get_running_loop()

    def handle_signal():
        worker.is_running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Signal handling on Windows event loop fallback
            pass

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())

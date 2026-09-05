from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths dynamically relative to this file
# parents[0] = worker/app/core, parents[1] = worker/app
# parents[2] = worker, parents[3] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PACKAGE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service name
    SERVICE_NAME: str = "Bug Reproduction Agent Worker"

    # Neon PostgreSQL Database
    NEON_DATABASE_URL: str = Field(
        default="",
        description="Neon serverless PostgreSQL database connection URL",
    )

    # Clerk Authentication
    CLERK_SECRET_KEY: str = Field(
        default="",
        description="Clerk Backend API Secret Key",
    )
    CLERK_PUBLISHABLE_KEY: str = Field(
        default="",
        description="Clerk Publishable Key",
    )

    # Google Gemini LLM API
    GEMINI_API_KEY: str = Field(
        default="",
        description="Google Gemini API key for reproduction agent reasoning",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.6-flash",
        description="Gemini model name for reproduction agent reasoning",
    )

    # Backblaze B2 Storage (S3-compatible API)
    # Endpoint format: https://s3.<region>.backblazeb2.com
    B2_KEY_ID: str = Field(
        default="",
        description="Backblaze B2 Key ID / Application Key ID",
    )
    B2_APPLICATION_KEY: str = Field(
        default="",
        description="Backblaze B2 Application Key",
    )
    B2_BUCKET_NAME: str = Field(
        default="bug-reproduction-artifacts",
        description="Backblaze B2 bucket name for reproduction logs and test output",
    )
    B2_ENDPOINT: str = Field(
        default="https://s3.us-west-004.backblazeb2.com",
        description="Backblaze B2 S3-compatible endpoint",
    )

    # Redis Connection
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for queue and message brokering",
    )

    # Worker queue parameters
    TASK_QUEUE_NAME: str = Field(
        default="reproduction_tasks",
        description="Redis queue name for bug reproduction tasks",
    )
    WORKER_CONCURRENCY: int = Field(
        default=5,
        description="Maximum concurrent reproduction tasks",
    )

    # Sandbox execution service
    SANDBOX_URL: str = Field(
        default="http://sandbox:8001",
        description="Base URL of the sandbox runner service",
    )

    # LangGraph graph parameters
    MAX_HYPOTHESES: int = Field(
        default=5,
        description="Maximum hypothesis retries before giving up on a bug report",
    )
    SANDBOX_TIMEOUT_SECONDS: int = Field(
        default=60,
        description="Per-run timeout forwarded to the sandbox service",
    )

    @property
    def neon_pg_dsn(self) -> str:
        """psycopg3-compatible DSN derived from NEON_DATABASE_URL."""
        url = self.NEON_DATABASE_URL
        # psycopg3 accepts the standard postgresql:// scheme directly
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    @property
    def neon_sa_url(self) -> str:
        """SQLAlchemy URL using psycopg3 dialect (postgresql+psycopg://)."""
        url = self.NEON_DATABASE_URL
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url



@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()

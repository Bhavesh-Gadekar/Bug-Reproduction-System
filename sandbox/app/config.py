"""Sandbox runner configuration via environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env search paths.
#
# Local layout:  <repo>/sandbox/app/config.py
#   parents[0] = <repo>/sandbox/app
#   parents[1] = <repo>/sandbox      (package root, has its own .env)
#   parents[2] = <repo>              (project root, has the shared .env)
#
# Docker layout: /app/app/config.py  (build context = ./sandbox)
#   parents[0] = /app/app
#   parents[1] = /app                (WORKDIR — env vars injected here or via docker-compose)
#   parents[2] = /                   (filesystem root — no .env here)
#
# Strategy: pass both candidates; pydantic-settings silently skips missing files.
_THIS_FILE = Path(__file__).resolve()
PACKAGE_ROOT = _THIS_FILE.parents[1]   # <repo>/sandbox  OR  /app
PROJECT_ROOT = _THIS_FILE.parents[2]   # <repo>          OR  /  (missing .env is fine)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PACKAGE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service metadata
    PROJECT_NAME: str = "Bug Reproduction Sandbox Runner"
    ENVIRONMENT: str = "development"
    PORT: int = 8001
    HOST: str = "0.0.0.0"

    # ──────────────────────────────────────────────
    # Container resource defaults (all overridable)
    # ──────────────────────────────────────────────

    # Fraction of CPUs available to each container (e.g. 0.5 = half a core)
    DEFAULT_CPU_LIMIT: float = Field(default=0.5, description="CPU quota per container")

    # Docker memory limit string (e.g. "256m", "512m")
    DEFAULT_MEMORY_LIMIT: str = Field(default="256m", description="Memory limit per container")

    # Max number of processes (PIDs) inside the container
    DEFAULT_PIDS_LIMIT: int = Field(default=64, description="PID limit per container")

    # Hard cap on timeout_seconds a caller may request
    MAX_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="Maximum allowed timeout for any single job",
    )

    # Extra seconds before the watchdog thread force-kills a container
    # that is still alive after the primary timeout fires.
    WATCHDOG_GRACE_SECONDS: int = Field(
        default=5,
        description="Grace period added to timeout before watchdog force-kills",
    )

    # Docker network to attach the container to.
    # "none" = full network isolation (production default).
    SANDBOX_NETWORK: str = Field(
        default="none",
        description='Docker network for sandboxed containers. Use "none" in production.',
    )

    # If True, attempt "docker pull <image>" before running when the image is absent.
    ALLOW_IMAGE_PULL: bool = Field(
        default=True,
        description="Pull the requested image if it is not present locally",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

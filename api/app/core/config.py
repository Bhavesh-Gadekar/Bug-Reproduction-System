from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    PROJECT_NAME: str = "Bug Reproduction Agent API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000"])

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
        description="Google Gemini API key for agent reasoning",
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
        description="Backblaze B2 bucket name for reproduction logs and artifacts",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()

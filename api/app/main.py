from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="FastAPI service for Bug Reproduction Agent orchestration",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "api",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/api/v1/health", tags=["Health"])
async def api_v1_health():
    """API v1 status endpoint."""
    return {
        "status": "healthy",
        "version": "v1",
        "services": {
            "database_configured": bool(settings.NEON_DATABASE_URL),
            "clerk_configured": bool(settings.CLERK_SECRET_KEY),
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "b2_configured": bool(settings.B2_KEY_ID and settings.B2_APPLICATION_KEY),
            "redis_configured": bool(settings.REDIS_URL),
        },
    }

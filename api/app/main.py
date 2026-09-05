from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webhooks import router as webhooks_router
from app.core.auth import AuthContext, get_current_auth_context
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

# Include Routers
app.include_router(webhooks_router)


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
            "clerk_webhook_configured": bool(settings.CLERK_WEBHOOK_SECRET),
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "b2_configured": bool(settings.B2_KEY_ID and settings.B2_APPLICATION_KEY),
            "redis_configured": bool(settings.REDIS_URL),
        },
    }


@app.get("/api/v1/me", tags=["Auth"])
async def get_current_user_profile(
    auth: AuthContext = Depends(get_current_auth_context),
):
    """
    Protected endpoint validating Clerk JWT and returning the resolved user and workspace context.
    """
    return {
        "clerk_user_id": auth.clerk_user_id,
        "user_id": str(auth.user_id) if auth.user_id else None,
        "workspace_id": str(auth.workspace_id) if auth.workspace_id else None,
        "clerk_org_id": auth.clerk_org_id,
        "email": auth.email,
        "role": auth.role,
    }

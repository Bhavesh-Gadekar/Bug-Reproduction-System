import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.bug_reports import router as bug_reports_router
from app.api.incidents import router as incidents_router
from app.api.metrics import router as metrics_router
from app.api.runs import router as runs_router
from app.api.webhooks import router as webhooks_router
from app.core.auth import AuthContext, get_current_auth_context
from app.core.config import get_settings
from app.core.redis import close_redis_pool, init_redis_pool

settings = get_settings()

api_logger = logging.getLogger("api.access")
api_logger.setLevel(logging.INFO)
if not api_logger.handlers:
    import sys
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    api_logger.addHandler(_h)

RUN_ID_REGEX = re.compile(r"/api/runs/([0-9a-fA-F\-]{36})")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Logs structured JSON for every HTTP request tagged with run_id and workspace_id."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.monotonic()

        # Extract run_id from path or headers
        run_id = request.headers.get("x-run-id")
        if not run_id:
            m = RUN_ID_REGEX.search(request.url.path)
            if m:
                run_id = m.group(1)

        # Extract workspace_id from query params or headers
        workspace_id = (
            request.headers.get("x-workspace-id")
            or request.query_params.get("workspace_id")
        )

        response = await call_next(request)

        # Fall back to request.state if set by auth or route
        if not workspace_id and hasattr(request.state, "workspace_id"):
            workspace_id = str(request.state.workspace_id)
        if not run_id and hasattr(request.state, "run_id"):
            run_id = str(request.state.run_id)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "service": "api",
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "run_id": str(run_id) if run_id else None,
            "workspace_id": str(workspace_id) if workspace_id else None,
            "client_ip": request.client.host if request.client else None,
        }
        api_logger.info(json.dumps(log_record))
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing external connections."""
    try:
        await init_redis_pool()
    except Exception:
        pass
    yield
    await close_redis_pool()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="FastAPI service for Bug Reproduction Agent orchestration",
    lifespan=lifespan,
)

# Structured Logging Middleware
app.add_middleware(StructuredLoggingMiddleware)

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
app.include_router(bug_reports_router)
app.include_router(runs_router)
app.include_router(metrics_router)
app.include_router(incidents_router)


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

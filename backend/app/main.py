from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import logging

from app.config import get_settings
from app.api import auth, documents, scan, tasks
from app.database import engine, Base
from app.utils.rate_limit import setup_rate_limiting
from app.middleware.csrf import CSRFMiddleware


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Validate critical security settings on startup
if (
    not settings.debug
    and settings.secret_key == "your-super-secret-key-change-in-production"
):
    raise ValueError(
        "CRITICAL: Default secret key detected in production mode! "
        "Set SECRET_KEY environment variable to a secure random value."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    os.makedirs(settings.upload_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    logger.info("Shutting down application")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Professional Document Scanner API",
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Rate limiting
setup_rate_limiting(app)

# CSRF protection middleware (must be added before CORS)
# This implements double-submit cookie pattern for state-changing requests
app.add_middleware(
    CSRFMiddleware,
    cookie_secure=not settings.debug,
    cookie_samesite="lax",
)

# CORS middleware with tightened security
# Only allow specific methods and headers needed by the application
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Origin",
    "X-Requested-With",
    "X-CSRF-Token",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,  # Required for httpOnly cookies
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
    expose_headers=["Content-Disposition"],  # For file downloads
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(scan.router, prefix="/api/scan", tags=["Scan"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Background Tasks"])


@app.get("/api/health")
async def health_check(request: Request):
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "celery_enabled": settings.celery_enabled,
        "rate_limit_enabled": settings.rate_limit_enabled,
    }

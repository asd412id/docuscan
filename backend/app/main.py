from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.api import auth, documents, scan, tasks
from app.database import engine, Base
from app.utils.rate_limit import setup_rate_limiting


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.upload_dir, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Professional Document Scanner API",
    lifespan=lifespan,
)

# Rate limiting
setup_rate_limiting(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

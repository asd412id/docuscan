"""
Rate limiting utilities for API endpoints.
Uses slowapi with Redis backend when available, falls back to in-memory storage.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from app.config import get_settings

settings = get_settings()


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request.
    Handles X-Forwarded-For header for reverse proxy setups.
    """
    # Check for X-Forwarded-For header (common in reverse proxy setups)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Check for X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client address
    return get_remote_address(request)


def create_limiter() -> Limiter:
    """
    Create rate limiter with appropriate storage backend.
    Uses Redis if available and enabled, otherwise in-memory.
    """
    storage_uri = None

    if settings.redis_enabled and settings.redis_url:
        # Use Redis for distributed rate limiting
        storage_uri = settings.redis_url

    return Limiter(
        key_func=get_client_ip,
        default_limits=[settings.rate_limit_default],
        storage_uri=storage_uri,
        enabled=settings.rate_limit_enabled,
    )


# Global limiter instance
limiter = create_limiter()


def setup_rate_limiting(app):
    """
    Set up rate limiting for FastAPI application.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Rate limit decorators for different endpoint types
def limit_auth(func):
    """Rate limit for authentication endpoints (login, register)."""
    return limiter.limit(settings.rate_limit_auth)(func)


def limit_upload(func):
    """Rate limit for file upload endpoints."""
    return limiter.limit(settings.rate_limit_upload)(func)


def limit_process(func):
    """Rate limit for processing endpoints."""
    return limiter.limit(settings.rate_limit_process)(func)


def limit_default(func):
    """Default rate limit for general endpoints."""
    return limiter.limit(settings.rate_limit_default)(func)

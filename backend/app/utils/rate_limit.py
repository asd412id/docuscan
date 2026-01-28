"""
Rate limiting utilities for API endpoints.
Uses slowapi with Redis backend when available, falls back to in-memory storage.
"""

import ipaddress
import logging
from typing import List, Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Default trusted proxy networks (localhost, docker, common cloud providers)
# In production, configure TRUSTED_PROXIES environment variable
DEFAULT_TRUSTED_PROXIES = [
    "127.0.0.0/8",  # Localhost
    "10.0.0.0/8",  # Private network
    "172.16.0.0/12",  # Private network (Docker default)
    "192.168.0.0/16",  # Private network
    "::1/128",  # IPv6 localhost
]


def parse_trusted_proxies() -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """
    Parse trusted proxy configuration from settings.
    Returns list of network objects for validation.
    """
    trusted_proxies = []
    proxy_list = getattr(settings, "trusted_proxies", None)

    if proxy_list:
        # Parse from comma-separated string in settings
        for proxy in proxy_list.split(","):
            proxy = proxy.strip()
            if proxy:
                try:
                    network = ipaddress.ip_network(proxy, strict=False)
                    trusted_proxies.append(network)
                except ValueError as e:
                    logger.warning(f"Invalid trusted proxy network: {proxy} - {e}")
    else:
        # Use defaults
        for proxy in DEFAULT_TRUSTED_PROXIES:
            try:
                network = ipaddress.ip_network(proxy, strict=False)
                trusted_proxies.append(network)
            except ValueError:
                pass

    return trusted_proxies


# Parse trusted proxies at module load
TRUSTED_PROXY_NETWORKS = parse_trusted_proxies()


def is_trusted_proxy(ip: str) -> bool:
    """
    Check if an IP address is from a trusted proxy.
    """
    try:
        addr = ipaddress.ip_address(ip)
        for network in TRUSTED_PROXY_NETWORKS:
            if addr in network:
                return True
    except ValueError:
        pass
    return False


def validate_ip_address(ip: str) -> bool:
    """
    Validate that an IP address is well-formed.
    Prevents injection attacks via forged headers.
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """
    Get client IP address from request with trusted proxy validation.

    Security considerations:
    - Only trust X-Forwarded-For/X-Real-IP if request comes from trusted proxy
    - Validate IP address format to prevent injection
    - Fall back to direct client address if headers are missing or invalid
    """
    # Get direct client address
    client_host = get_remote_address(request)

    # Check if request comes from trusted proxy
    if client_host and is_trusted_proxy(client_host):
        # Check for X-Forwarded-For header (common in reverse proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (original client)
            # Format: "client, proxy1, proxy2, ..."
            client_ip = forwarded_for.split(",")[0].strip()

            # Validate the IP address format
            if validate_ip_address(client_ip):
                return client_ip
            else:
                logger.warning(f"Invalid X-Forwarded-For IP: {client_ip}")

        # Check for X-Real-IP header (nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            real_ip = real_ip.strip()
            if validate_ip_address(real_ip):
                return real_ip
            else:
                logger.warning(f"Invalid X-Real-IP: {real_ip}")
    else:
        # Request not from trusted proxy - ignore forwarded headers
        # Log if headers are present but ignored (potential spoofing attempt)
        if request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP"):
            logger.warning(
                f"Ignoring forwarded headers from untrusted source: {client_host}"
            )

    # Fall back to direct client address
    return client_host or "127.0.0.1"


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

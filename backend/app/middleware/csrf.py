"""
CSRF Protection Middleware for FastAPI.

Implements the double-submit cookie pattern:
1. Server sets a CSRF token in a cookie (readable by JavaScript)
2. Client must send the same token in a header (X-CSRF-Token)
3. Server validates that cookie token matches header token

This works because:
- Attackers can't read cookies from other domains (same-origin policy)
- Attackers can't set custom headers on cross-origin requests
- Combined with SameSite cookies, provides robust CSRF protection
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    generate_csrf_token,
    validate_csrf_token,
    is_csrf_exempt,
)
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using double-submit cookie pattern.

    For state-changing requests (POST, PUT, DELETE, PATCH):
    1. Validates that X-CSRF-Token header matches csrf_token cookie
    2. If validation fails, returns 403 Forbidden

    For all requests:
    1. Sets/refreshes CSRF token cookie if not present
    """

    def __init__(
        self,
        app: ASGIApp,
        cookie_secure: bool = True,
        cookie_samesite: str = "lax",
    ):
        super().__init__(app)
        self.cookie_secure = cookie_secure and not settings.debug
        self.cookie_samesite = cookie_samesite

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get current CSRF token from cookie
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)

        # Check if this request needs CSRF validation
        if not is_csrf_exempt(request.url.path, request.method):
            # Get CSRF token from header
            csrf_header = request.headers.get(CSRF_HEADER_NAME)

            # Validate tokens match
            if not validate_csrf_token(csrf_cookie, csrf_header):
                logger.warning(
                    f"CSRF validation failed for {request.method} {request.url.path} "
                    f"from {request.client.host if request.client else 'unknown'}"
                )
                return Response(
                    content='{"detail": "CSRF validation failed"}',
                    status_code=403,
                    media_type="application/json",
                )

        # Process the request
        response = await call_next(request)

        # Set or refresh CSRF cookie if not present
        if not csrf_cookie:
            new_token = generate_csrf_token()
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=new_token,
                httponly=False,  # Must be readable by JavaScript
                secure=self.cookie_secure,
                samesite=self.cookie_samesite,
                path="/",
                max_age=86400,  # 24 hours
            )

        return response


def setup_csrf_protection(app: ASGIApp) -> None:
    """
    Set up CSRF protection middleware on FastAPI app.

    Args:
        app: FastAPI application instance
    """
    app.add_middleware(
        CSRFMiddleware,
        cookie_secure=not settings.debug,
        cookie_samesite="lax",
    )

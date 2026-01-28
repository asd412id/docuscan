"""
Middleware package for DocuScan.
"""

from app.middleware.csrf import CSRFMiddleware, setup_csrf_protection

__all__ = ["CSRFMiddleware", "setup_csrf_protection"]

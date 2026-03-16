# app/api/middleware.py
# HTTP middleware applied to every response.
# Add more classes here as the app grows (e.g. request logging, tracing).

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Inject security-related HTTP response headers on every reply.
    These are a defence-in-depth measure on top of Nginx headers.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]          = "SAMEORIGIN"
        response.headers["Referrer-Policy"]          = "no-referrer-when-downgrade"
        response.headers["X-XSS-Protection"]         = "1; mode=block"
        return response

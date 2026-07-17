"""Middlewares de produção: request-id + log de acesso e security headers."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import reset_request_id, set_request_id

access_logger = logging.getLogger("meteoro.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

# CSP do portal: permite Leaflet via unpkg e tiles/imagens externas enquanto as
# bibliotecas não são vendorizadas (Etapa C10b aperta esta política).
PORTAL_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com; "
    "style-src 'self' https://unpkg.com 'unsafe-inline'; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "frame-ancestors 'none'"
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gera/propaga X-Request-ID e emite uma linha de log por requisição."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            access_logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "client": request.client.host if request.client else None,
                    }
                },
            )
            return response
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if request.url.path.startswith("/portal"):
            response.headers.setdefault("Content-Security-Policy", PORTAL_CSP)
        return response

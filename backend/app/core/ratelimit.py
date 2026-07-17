"""Rate limiting por IP para a superfície pública da API.

Janela fixa de 60 segundos, em memória de processo — adequado à produção
assistida (instância única). Em ambiente multi-instância, migrar o estado
para Redis (previsto no Bloco D do plano).
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.settings import settings

logger = logging.getLogger("meteoro.ratelimit")

PUBLIC_PREFIX = "/api/v1/public"
CSV_SUFFIX = ".csv"
WINDOW_SECONDS = 60
_MAX_TRACKED_KEYS = 10_000

# (bucket, ip) -> [contagem, início_da_janela]
_hits: dict[tuple[str, str], list[float]] = {}


def reset_rate_limits() -> None:
    """Zera o estado (usado em testes)."""
    _hits.clear()


def _purge_expired(now: float) -> None:
    if len(_hits) < _MAX_TRACKED_KEYS:
        return
    expired = [key for key, (_, start) in _hits.items() if now - start >= WINDOW_SECONDS]
    for key in expired:
        _hits.pop(key, None)


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if not settings.public_rate_limit_enabled or not path.startswith(PUBLIC_PREFIX):
            return await call_next(request)

        if path.endswith(CSV_SUFFIX):
            bucket, limit = "public_csv", settings.public_csv_rate_limit_per_minute
        else:
            bucket, limit = "public", settings.public_rate_limit_per_minute

        client_ip = request.client.host if request.client else "desconhecido"
        now = time.monotonic()
        _purge_expired(now)

        key = (bucket, client_ip)
        entry = _hits.get(key)
        if entry is None or now - entry[1] >= WINDOW_SECONDS:
            _hits[key] = [1.0, now]
        else:
            entry[0] += 1
            if entry[0] > limit:
                retry_after = max(1, int(WINDOW_SECONDS - (now - entry[1])))
                logger.warning(
                    "Rate limit excedido",
                    extra={
                        "extra_fields": {
                            "client": client_ip,
                            "path": path,
                            "bucket": bucket,
                            "limit_per_minute": limit,
                        }
                    },
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "Limite de requisições excedido para os dados públicos. "
                            f"Tente novamente em {retry_after} segundos."
                        )
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        return await call_next(request)

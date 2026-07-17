import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.health import readiness_report
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.request_context import get_request_id
from app.core.settings import settings

configure_logging()
error_logger = logging.getLogger("meteoro.error")

_is_production = settings.environment.strip().lower() == "production"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    # Em produção a documentação interativa fica desabilitada.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Ordem efetiva de execução: RequestContext -> SecurityHeaders -> GZip -> rotas.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Nunca vaza stacktrace ao cliente; registra com request_id para correlação."""
    error_logger.error(
        "Exceção não tratada em %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno do servidor. O evento foi registrado.",
            "request_id": get_request_id(),
        },
    )


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: o processo está de pé e respondendo."""
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/ready", tags=["health"])
def health_ready() -> JSONResponse:
    """Readiness: dependências críticas (banco, storage, Redis) disponíveis.

    Retorna 503 quando alguma dependência obrigatória está indisponível,
    permitindo que orquestradores e proxies retirem a instância do tráfego.
    """
    report, critical_ok = readiness_report()
    return JSONResponse(status_code=200 if critical_ok else 503, content=report)


app.include_router(api_router, prefix="/api/v1")

portal_path = Path(__file__).resolve().parents[2] / "frontend"
if portal_path.is_dir():
    app.mount("/portal", StaticFiles(directory=portal_path, html=True), name="portal")

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.health import readiness_report
from app.core.settings import settings

_is_production = settings.environment.strip().lower() == "production"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    # Em produção a documentação interativa fica desabilitada.
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
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

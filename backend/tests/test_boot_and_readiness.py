"""Etapa 5 — boot seguro e endpoints de saúde."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import INSECURE_JWT_DEFAULT, Settings


def _settings(**overrides) -> Settings:
    """Constrói Settings isolado de .env e variáveis de ambiente do host."""
    return Settings(_env_file=None, **overrides)


def test_producao_recusa_segredo_default() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(environment="production", jwt_secret_key=INSECURE_JWT_DEFAULT)
    assert "JWT_SECRET_KEY" in str(excinfo.value)


def test_producao_recusa_segredo_curto() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _settings(environment="production", jwt_secret_key="curto-demais")
    assert "32" in str(excinfo.value)


def test_producao_aceita_segredo_forte() -> None:
    config = _settings(
        environment="production",
        jwt_secret_key="a" * 48,
    )
    assert config.environment == "production"


def test_desenvolvimento_tolera_segredo_default() -> None:
    config = _settings(environment="development", jwt_secret_key=INSECURE_JWT_DEFAULT)
    assert config.jwt_secret_key == INSECURE_JWT_DEFAULT


def test_health_liveness(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_readiness_reporta_componentes(client) -> None:
    response = client.get("/health/ready")
    payload = response.json()
    assert response.status_code in {200, 503}
    assert payload["status"] in {"ready", "degraded", "not_ready"}
    assert set(payload["components"]) == {"database", "raw_storage", "redis"}
    for component in payload["components"].values():
        assert component["status"] in {"ok", "unavailable"}
        assert isinstance(component["required"], bool)

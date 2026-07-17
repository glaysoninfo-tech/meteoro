"""Etapa 8 — sessão do operador: refresh rotativo, revogação e cookie httpOnly."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.modules.identity.refresh import REFRESH_COOKIE_NAME
from tests.conftest import bootstrap_admin


def _login(client: TestClient) -> dict[str, str]:
    bootstrap_admin(client)
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.org", "password": "senha-forte-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_planta_cookie_httponly(client: TestClient) -> None:
    response_login = None
    bootstrap_admin(client)
    response_login = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.org", "password": "senha-forte-123"},
    )
    set_cookie = response_login.headers.get("set-cookie", "")
    assert REFRESH_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie.lower() or "samesite=strict" in set_cookie.lower()


def test_refresh_renova_access_token_e_rotaciona_cookie(client: TestClient) -> None:
    _login(client)
    primeiro_cookie = client.cookies.get(REFRESH_COOKIE_NAME)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    segundo_cookie = client.cookies.get(REFRESH_COOKIE_NAME)
    assert segundo_cookie and segundo_cookie != primeiro_cookie


def test_token_rotacionado_nao_pode_ser_reusado(client: TestClient) -> None:
    _login(client)
    cookie_antigo = client.cookies.get(REFRESH_COOKIE_NAME)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    # Reapresenta o cookie antigo (já rotacionado): deve ser rejeitado.
    client.cookies.set(REFRESH_COOKIE_NAME, cookie_antigo)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_reuso_revoga_todas_as_sessoes_do_usuario(client: TestClient) -> None:
    _login(client)
    cookie_antigo = client.cookies.get(REFRESH_COOKIE_NAME)
    refresh_ok = client.post("/api/v1/auth/refresh")
    cookie_novo = client.cookies.get(REFRESH_COOKIE_NAME)
    assert refresh_ok.status_code == 200
    # Reuso do antigo dispara a revogação em família...
    client.cookies.set(REFRESH_COOKIE_NAME, cookie_antigo)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    # ...derrubando também o token novo.
    client.cookies.set(REFRESH_COOKIE_NAME, cookie_novo)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revoga_sessao(client: TestClient) -> None:
    _login(client)
    cookie = client.cookies.get(REFRESH_COOKIE_NAME)
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set(REFRESH_COOKIE_NAME, cookie)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_sem_cookie_retorna_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401

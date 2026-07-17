from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.core.settings import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.identity.models import RoleModel, UserModel, UserRoleModel

# Quando definida (CI ou desenvolvedor com Postgres local), a suíte roda contra
# PostgreSQL/PostGIS com schema criado pela cadeia REAL de migrações Alembic —
# o mesmo caminho da produção. Sem ela, mantém SQLite em memória (rápido, local).
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@pytest.fixture(autouse=True)
def isolated_runtime_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(settings, "ingestion_storage_path", str(tmp_path / "raw"))
    monkeypatch.setattr(settings, "ingestion_network_allowed_hosts", "api.example.org,*.dados.gov.br")
    monkeypatch.setattr(settings, "ingestion_network_allowed_ports", "443,1883,4840")
    monkeypatch.setattr(settings, "ingestion_http_allowed_schemes", "https")
    monkeypatch.setattr(settings, "ingestion_s3_allowed_buckets", "meteoro-test-bucket")
    monkeypatch.setattr(settings, "ingestion_scheduler_enabled", False)
    yield


@pytest.fixture(scope="session")
def _postgres_engine() -> Generator[Engine, None, None]:
    """Engine de sessão para PostgreSQL: schema zerado + migrações reais."""
    engine = create_engine(TEST_DATABASE_URL, future=True, pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    previous_url = settings.database_url
    settings.database_url = TEST_DATABASE_URL
    try:
        alembic_command.upgrade(AlembicConfig("alembic.ini"), "head")
    finally:
        settings.database_url = previous_url
    try:
        yield engine
    finally:
        engine.dispose()


def _clean_database(engine: Engine) -> None:
    """Esvazia todas as tabelas do domínio preservando o schema migrado."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def session_factory(request: pytest.FixtureRequest) -> Generator[sessionmaker[Session], None, None]:
    if TEST_DATABASE_URL:
        engine = request.getfixturevalue("_postgres_engine")
        _clean_database(engine)
        yield sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
        return

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def bootstrap_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "name": "Admin Meteoro",
            "email": "admin@example.org",
            "password": "senha-forte-123",
            "organization_name": "Cidade Teste",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_role_headers(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    role_name: str,
) -> dict[str, str]:
    session = session_factory()
    try:
        admin = session.scalar(select(UserModel).where(UserModel.email == "admin@example.org"))
        role = session.scalar(select(RoleModel).where(RoleModel.name == role_name))
        assert admin is not None
        assert role is not None
        now = datetime.now(tz=timezone.utc)
        user = UserModel(
            organization_id=admin.organization_id,
            name=f"Usuário {role_name}",
            email=email,
            password_hash=hash_password("senha-forte-456"),
            identity_provider="local",
            identity_provider_subject=None,
            status="active",
            mfa_enabled=False,
            created_at=now,
        )
        session.add(user)
        session.flush()
        session.add(
            UserRoleModel(
                user_id=user.user_id,
                role_id=role.role_id,
                organization_id=admin.organization_id,
                valid_from=now,
                valid_to=None,
                assigned_at=now,
            )
        )
        session.commit()
        token, _expires_at = create_access_token(
            user_id=user.user_id,
            organization_id=user.organization_id,
            roles=[role_name],
        )
        return {"Authorization": f"Bearer {token}"}
    finally:
        session.close()


def create_authority_headers(session_factory: sessionmaker[Session]) -> dict[str, str]:
    return create_role_headers(
        session_factory,
        email="autoridade@example.org",
        role_name="authority_approver",
    )

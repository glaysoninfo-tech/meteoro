"""Ciclo de vida do refresh token: emissão, rotação e revogação.

Regras:
- Rotação obrigatória: cada uso emite um token novo e revoga o anterior.
- Reuso de token já rotacionado/revogado é tratado como possível roubo:
  todas as sessões do usuário são revogadas.
- Armazenamos apenas SHA-256; o valor bruto nunca toca o banco nem os logs.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.identity.models import RefreshTokenModel, UserModel

REFRESH_COOKIE_NAME = "meteoro_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
_TOKEN_BYTES = 48


class RefreshTokenError(ValueError):
    """Sessão inválida, expirada ou revogada."""


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """SQLite devolve datetimes naive; normaliza para UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def issue_refresh_token(db: Session, user: UserModel) -> str:
    now = datetime.now(tz=timezone.utc)
    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(
        RefreshTokenModel(
            user_id=user.user_id,
            organization_id=user.organization_id,
            token_hash=_hash(raw_token),
            issued_at=now,
            expires_at=now + timedelta(hours=settings.refresh_token_expire_hours),
        )
    )
    db.commit()
    return raw_token


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str, UserModel]:
    """Valida o token, revoga-o e emite um sucessor. Retorna (novo_token, usuário)."""
    now = datetime.now(tz=timezone.utc)
    record = db.scalar(
        select(RefreshTokenModel).where(RefreshTokenModel.token_hash == _hash(raw_token))
    )
    if record is None:
        raise RefreshTokenError("Sessão não reconhecida. Entre novamente.")
    if record.revoked_at is not None:
        # Token já rotacionado sendo reapresentado: revoga a família inteira.
        revoke_all_for_user(db, user_id=record.user_id)
        raise RefreshTokenError("Sessão revogada por segurança. Entre novamente.")
    if _aware(record.expires_at) <= now:
        raise RefreshTokenError("Sessão expirada. Entre novamente.")

    user = db.get(UserModel, record.user_id)
    if user is None or user.status != "active":
        raise RefreshTokenError("Usuário indisponível para renovação de sessão.")

    new_raw = secrets.token_urlsafe(_TOKEN_BYTES)
    successor = RefreshTokenModel(
        user_id=user.user_id,
        organization_id=user.organization_id,
        token_hash=_hash(new_raw),
        issued_at=now,
        expires_at=now + timedelta(hours=settings.refresh_token_expire_hours),
    )
    db.add(successor)
    db.flush()
    record.revoked_at = now
    record.replaced_by_token_id = successor.token_id
    db.commit()
    return new_raw, user


def revoke_refresh_token(db: Session, raw_token: str) -> bool:
    record = db.scalar(
        select(RefreshTokenModel).where(RefreshTokenModel.token_hash == _hash(raw_token))
    )
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = datetime.now(tz=timezone.utc)
    db.commit()
    return True


def revoke_all_for_user(db: Session, user_id: str) -> int:
    now = datetime.now(tz=timezone.utc)
    result = db.execute(
        update(RefreshTokenModel)
        .where(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
    return int(result.rowcount or 0)

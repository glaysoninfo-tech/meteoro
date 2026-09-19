from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClientError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.identity.keycloak import decode_keycloak_token
from app.modules.identity.schemas import CurrentUser
from app.modules.identity.service import identity_service

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso não informado.",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esquema de autenticação inválido.",
        )

    auth_errors: list[str] = []

    if settings.auth_mode in {"local", "hybrid"}:
        try:
            return _authenticate_local_token(credentials.credentials, db)
        except HTTPException as exc:
            auth_errors.append(str(exc.detail))

    if settings.auth_mode in {"keycloak", "hybrid"}:
        try:
            return _authenticate_keycloak_token(credentials.credentials, db)
        except HTTPException as exc:
            auth_errors.append(str(exc.detail))

    detail = "Falha ao autenticar token."
    if auth_errors:
        detail = " | ".join(auth_errors)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def require_roles(*required_roles: str) -> Callable[[CurrentUser], CurrentUser]:
    required = set(required_roles)

    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not required.intersection(current_user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Perfil sem permissão para esta operação.",
            )
        return current_user

    return dependency


def can_access_organization(current_user: CurrentUser, organization_id: str) -> bool:
    if "admin_general" in current_user.roles:
        return True
    return current_user.organization_id == organization_id


def _authenticate_local_token(token: str, db: Session) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local expirado.",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local inválido.",
        ) from exc

    user_id = payload.get("sub")
    organization_id = payload.get("org")
    if not user_id or not organization_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local sem dados obrigatórios.",
        )

    user = identity_service.get_user_by_id(db=db, user_id=user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário local inválido ou inativo.",
        )
    if user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token local incompatível com a organização do usuário.",
        )

    roles = identity_service.get_active_roles(
        db=db,
        user_id=user.user_id,
        organization_id=user.organization_id,
    )
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário local sem perfil ativo.",
        )

    return CurrentUser(
        user_id=user.user_id,
        organization_id=user.organization_id,
        name=user.name,
        email=user.email,
        roles=roles,
    )


def _authenticate_keycloak_token(token: str, db: Session) -> CurrentUser:
    try:
        claims = decode_keycloak_token(token)
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Keycloak expirado.",
        ) from exc
    except (InvalidTokenError, PyJWKClientError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token Keycloak inválido: {exc}",
        ) from exc

    subject = claims.get("sub")
    email = claims.get("email") or claims.get("preferred_username")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token Keycloak sem subject (sub).",
        )

    user = identity_service.get_user_by_identity_subject(
        db=db,
        identity_provider="keycloak",
        identity_subject=subject,
    )

    if user is None:
        if email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Usuário Keycloak não vinculado na plataforma. "
                    f"Solicite vínculo administrativo para o e-mail '{email}'."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário Keycloak não vinculado na plataforma.",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário Keycloak inativo.",
        )

    roles = identity_service.get_active_roles(
        db=db,
        user_id=user.user_id,
        organization_id=user.organization_id,
    )
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário Keycloak sem perfil ativo.",
        )

    return CurrentUser(
        user_id=user.user_id,
        organization_id=user.organization_id,
        name=user.name,
        email=user.email,
        roles=roles,
    )

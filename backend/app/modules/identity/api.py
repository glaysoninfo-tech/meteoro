from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.modules.audit.service import audit_service
from app.modules.identity.refresh import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    RefreshTokenError,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.modules.identity.dependencies import can_access_organization, get_current_user, require_roles
from app.modules.identity.schemas import (
    BootstrapAdminRequest,
    CurrentUser,
    KeycloakLinkRequest,
    KeycloakLinkResponse,
    TokenRequest,
    TokenResponse,
)
from app.modules.identity.service import identity_service

router = APIRouter()


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.refresh_token_expire_hours * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.environment.strip().lower() == "production",
    )


@router.post(
    "/bootstrap-admin",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_admin(payload: BootstrapAdminRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if settings.auth_mode == "keycloak":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap local desabilitado em modo keycloak. Use AUTH_MODE=hybrid para inicialização.",
        )

    try:
        user = identity_service.bootstrap_admin(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    roles = identity_service.get_active_roles(
        db=db,
        user_id=user.user_id,
        organization_id=user.organization_id,
    )
    access_token, expires_at = create_access_token(
        user_id=user.user_id,
        organization_id=user.organization_id,
        roles=roles,
    )
    audit_service.create_event(
        db=db,
        module="identity",
        action="auth.bootstrap_admin",
        actor=user.email,
        organization_id=user.organization_id,
        resource_type="user",
        resource_id=user.user_id,
    )
    return TokenResponse(access_token=access_token, expires_at_utc=expires_at)


@router.post("/token", response_model=TokenResponse)
def create_token(
    payload: TokenRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    if settings.auth_mode == "keycloak":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Login local desabilitado: autentique via Keycloak.",
        )

    try:
        user, roles = identity_service.authenticate(
            db=db,
            email=payload.email,
            password=payload.password,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    access_token, expires_at = create_access_token(
        user_id=user.user_id,
        organization_id=user.organization_id,
        roles=roles,
    )
    audit_service.create_event(
        db=db,
        module="identity",
        action="auth.login",
        actor=user.email,
        organization_id=user.organization_id,
        resource_type="user",
        resource_id=user.user_id,
    )
    _set_refresh_cookie(response, issue_refresh_token(db, user))
    return TokenResponse(access_token=access_token, expires_at_utc=expires_at)


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Renova a sessão a partir do cookie httpOnly, com rotação do token."""
    if settings.auth_mode == "keycloak":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Renovação local desabilitada: autentique via Keycloak.",
        )
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nenhuma sessão ativa para renovar.",
        )
    try:
        new_raw, user = rotate_refresh_token(db, raw_token)
    except RefreshTokenError as exc:
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    roles = identity_service.get_active_roles(
        db=db,
        user_id=user.user_id,
        organization_id=user.organization_id,
    )
    access_token, expires_at = create_access_token(
        user_id=user.user_id,
        organization_id=user.organization_id,
        roles=roles,
    )
    _set_refresh_cookie(response, new_raw)
    return TokenResponse(access_token=access_token, expires_at_utc=expires_at)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """Revoga a sessão atual e limpa o cookie (idempotente)."""
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        revoke_refresh_token(db, raw_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return {"detail": "Sessão encerrada."}


@router.get("/me", response_model=CurrentUser)
def get_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user


@router.get("/provider")
def auth_provider() -> dict[str, str | None]:
    return {
        "auth_mode": settings.auth_mode,
        "keycloak_issuer_url": settings.keycloak_issuer_url,
        "keycloak_audience": settings.keycloak_audience,
    }


@router.post("/admin/keycloak/link", response_model=KeycloakLinkResponse)
def link_keycloak_user(
    payload: KeycloakLinkRequest,
    current_user: CurrentUser = Depends(require_roles("admin_general")),
    db: Session = Depends(get_db),
) -> KeycloakLinkResponse:
    try:
        user = identity_service.link_user_to_keycloak(
            db=db,
            email=payload.email,
            keycloak_subject=payload.keycloak_subject,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if not can_access_organization(current_user, user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para administrar este usuário.",
        )

    if user.identity_provider_subject is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vínculo de identidade externa não persistido.",
        )

    audit_service.create_event(
        db=db,
        module="identity",
        action="identity.keycloak.linked",
        actor=current_user.email,
        organization_id=user.organization_id,
        resource_type="user",
        resource_id=user.user_id,
    )
    return KeycloakLinkResponse(
        user_id=user.user_id,
        organization_id=user.organization_id,
        email=user.email,
        identity_provider=user.identity_provider,
        identity_provider_subject=user.identity_provider_subject,
    )

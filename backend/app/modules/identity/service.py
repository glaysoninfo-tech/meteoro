from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.identity.models import (
    OrganizationModel,
    RoleModel,
    UserModel,
    UserRoleModel,
)
from app.modules.identity.schemas import BootstrapAdminRequest

DEFAULT_ROLES: tuple[tuple[str, str, str], ...] = (
    ("admin_general", "Administrador geral da plataforma", "global"),
    ("operator", "Operador municipal", "organization"),
    ("authority_approver", "Autoridade aprovadora de protocolos", "organization"),
    ("analyst", "Analista técnico", "organization"),
    ("auditor", "Auditoria e controle interno", "organization"),
)


class IdentityService:
    def bootstrap_admin(self, db: Session, payload: BootstrapAdminRequest) -> UserModel:
        user_count = db.scalar(select(func.count()).select_from(UserModel))
        if user_count and user_count > 0:
            raise ValueError("Bootstrap já executado: existe usuário cadastrado.")

        now = datetime.now(tz=timezone.utc)
        organization = OrganizationModel(
            organization_type="MUNICIPAL",
            display_name=payload.organization_name,
            status="active",
            created_at=now,
        )
        db.add(organization)
        db.flush()

        self._ensure_default_roles(db=db, now=now)

        user = UserModel(
            organization_id=organization.organization_id,
            name=payload.name,
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            identity_provider="local",
            identity_provider_subject=None,
            status="active",
            mfa_enabled=False,
            created_at=now,
        )
        db.add(user)
        db.flush()

        admin_role = self._get_role_by_name(db=db, role_name="admin_general")
        user_role = UserRoleModel(
            user_id=user.user_id,
            role_id=admin_role.role_id,
            organization_id=organization.organization_id,
            valid_from=now,
            valid_to=None,
            assigned_at=now,
        )
        db.add(user_role)
        db.commit()
        db.refresh(user)
        return user

    def authenticate(self, db: Session, email: str, password: str) -> tuple[UserModel, list[str]]:
        stmt = select(UserModel).where(UserModel.email == email.lower())
        user = db.scalar(stmt)
        if user is None:
            raise PermissionError("Credenciais inválidas.")
        if user.identity_provider == "keycloak":
            raise PermissionError("Usuário deve autenticar via Keycloak.")
        if user.status != "active":
            raise PermissionError("Usuário inativo.")
        if not verify_password(password=password, password_hash=user.password_hash):
            raise PermissionError("Credenciais inválidas.")

        roles = self.get_active_roles(db=db, user_id=user.user_id, organization_id=user.organization_id)
        if not roles:
            raise PermissionError("Usuário sem perfil ativo.")

        user.last_login_at = datetime.now(tz=timezone.utc)
        db.commit()
        db.refresh(user)
        return user, roles

    def get_active_roles(self, db: Session, user_id: str, organization_id: str) -> list[str]:
        now = datetime.now(tz=timezone.utc)
        stmt = (
            select(RoleModel.name)
            .join(UserRoleModel, UserRoleModel.role_id == RoleModel.role_id)
            .where(
                and_(
                    UserRoleModel.user_id == user_id,
                    UserRoleModel.organization_id == organization_id,
                    UserRoleModel.valid_from <= now,
                    or_(UserRoleModel.valid_to.is_(None), UserRoleModel.valid_to > now),
                )
            )
            .order_by(RoleModel.name.asc())
        )
        return [row for row in db.scalars(stmt).all()]

    def get_user_by_id(self, db: Session, user_id: str) -> UserModel | None:
        return db.get(UserModel, user_id)

    def get_user_by_email(self, db: Session, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email == email.lower())
        return db.scalar(stmt)

    def get_user_by_identity_subject(
        self,
        db: Session,
        identity_provider: str,
        identity_subject: str,
    ) -> UserModel | None:
        stmt = select(UserModel).where(
            and_(
                UserModel.identity_provider == identity_provider,
                UserModel.identity_provider_subject == identity_subject,
            )
        )
        return db.scalar(stmt)

    def bind_user_identity(
        self,
        db: Session,
        user: UserModel,
        identity_provider: str,
        identity_subject: str,
    ) -> UserModel:
        if (
            user.identity_provider_subject is not None
            and user.identity_provider_subject != identity_subject
        ):
            raise PermissionError("Usuário já vinculado a outro subject de identidade.")
        if user.identity_provider not in {"local", "keycloak"}:
            raise PermissionError("Provedor de identidade do usuário não suportado.")

        user.identity_provider = identity_provider
        user.identity_provider_subject = identity_subject
        db.commit()
        db.refresh(user)
        return user

    def link_user_to_keycloak(
        self,
        db: Session,
        *,
        email: str,
        keycloak_subject: str,
    ) -> UserModel:
        user = self.get_user_by_email(db=db, email=email)
        if user is None:
            raise LookupError(f"Usuário com e-mail '{email}' não encontrado.")

        existing = self.get_user_by_identity_subject(
            db=db,
            identity_provider="keycloak",
            identity_subject=keycloak_subject,
        )
        if existing is not None and existing.user_id != user.user_id:
            raise ValueError("Subject do Keycloak já está vinculado a outro usuário.")

        if (
            user.identity_provider == "keycloak"
            and user.identity_provider_subject == keycloak_subject
        ):
            return user

        return self.bind_user_identity(
            db=db,
            user=user,
            identity_provider="keycloak",
            identity_subject=keycloak_subject,
        )

    def _ensure_default_roles(self, db: Session, now: datetime) -> None:
        existing_stmt = select(RoleModel.name)
        existing_names = {name for name in db.scalars(existing_stmt).all()}
        for role_name, description, scope in DEFAULT_ROLES:
            if role_name in existing_names:
                continue
            db.add(
                RoleModel(
                    name=role_name,
                    description=description,
                    scope=scope,
                    created_at=now,
                )
            )
        db.flush()

    def _get_role_by_name(self, db: Session, role_name: str) -> RoleModel:
        stmt = select(RoleModel).where(RoleModel.name == role_name)
        role = db.scalar(stmt)
        if role is None:
            raise LookupError(f"Perfil '{role_name}' não encontrado.")
        return role


identity_service = IdentityService()

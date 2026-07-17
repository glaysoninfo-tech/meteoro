from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class BootstrapAdminRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=120)


class TokenRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at_utc: datetime


class CurrentUser(BaseModel):
    user_id: str
    organization_id: str
    name: str
    email: EmailStr
    roles: list[str]


class KeycloakLinkRequest(BaseModel):
    email: EmailStr
    keycloak_subject: str = Field(min_length=3, max_length=160)


class KeycloakLinkResponse(BaseModel):
    user_id: str
    organization_id: str
    email: EmailStr
    identity_provider: str
    identity_provider_subject: str

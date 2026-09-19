from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.core.settings import settings


def get_keycloak_jwks_url() -> str:
    if settings.keycloak_jwks_url:
        return settings.keycloak_jwks_url
    if settings.keycloak_issuer_url is None:
        raise RuntimeError("KEYCLOAK_ISSUER_URL não configurado.")
    issuer = settings.keycloak_issuer_url.rstrip("/")
    return f"{issuer}/protocol/openid-connect/certs"


@lru_cache(maxsize=1)
def get_jwk_client() -> PyJWKClient:
    return PyJWKClient(get_keycloak_jwks_url())


def decode_keycloak_token(token: str) -> dict:
    if settings.keycloak_issuer_url is None:
        raise RuntimeError("KEYCLOAK_ISSUER_URL não configurado.")

    signing_key = get_jwk_client().get_signing_key_from_jwt(token)
    decode_kwargs: dict = {
        "jwt": token,
        "key": signing_key.key,
        "algorithms": [settings.keycloak_jwt_algorithm],
        "issuer": settings.keycloak_issuer_url,
        "options": {"verify_aud": settings.keycloak_audience is not None},
    }
    if settings.keycloak_audience is not None:
        decode_kwargs["audience"] = settings.keycloak_audience

    return jwt.decode(**decode_kwargs)


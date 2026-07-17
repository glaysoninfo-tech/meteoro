from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets

import jwt

from app.core.settings import settings

PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 210_000
PBKDF2_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("utf-8")
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    return f"{PBKDF2_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) != 3:
        return False

    iterations_raw, salt_b64, digest_b64 = parts
    if not iterations_raw.isdigit():
        return False

    expected_digest = base64.b64decode(digest_b64.encode("utf-8"))
    salt = base64.b64decode(salt_b64.encode("utf-8"))
    computed_digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        int(iterations_raw),
    )
    return hmac.compare_digest(expected_digest, computed_digest)


def create_access_token(
    user_id: str,
    organization_id: str,
    roles: list[str],
) -> tuple[str, datetime]:
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(
        payload=payload,
        key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded, expires_at


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        jwt=token,
        key=settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


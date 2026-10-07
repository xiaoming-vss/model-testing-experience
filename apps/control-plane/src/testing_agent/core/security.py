from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from jwt.utils import base64url_decode

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import ErrBadRequest, ErrUnauthorized

_BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(raw: str) -> str:
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > _BCRYPT_MAX_PASSWORD_BYTES:
        raise ErrBadRequest()
    return bcrypt.hashpw(raw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > _BCRYPT_MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw_bytes, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "userId": user_id,
        "exp": now + timedelta(hours=settings.jwt_expire_hours),
        "iat": now,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_key, algorithm="HS256")


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    expires_at: datetime


def access_token_hash(token: str) -> str:
    # Equivalent base64 signature encodings must share a revocation identity.
    # Call only after signature validation by parse_access_token_claims.
    signed_payload, signature = token.rsplit(".", 1)
    return sha256(signed_payload.encode("utf-8") + b"." + base64url_decode(signature)).hexdigest()


def parse_access_token_claims(token: str, settings: Settings | None = None) -> AccessTokenClaims:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_key, algorithms=["HS256"], options={"require": ["exp", "userId"]}
        )
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError, OSError) as exc:
        raise ErrUnauthorized() from exc
    user_id = payload.get("userId")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ErrUnauthorized()
    return AccessTokenClaims(user_id=user_id, expires_at=expires_at)


def parse_access_token(token: str, settings: Settings | None = None) -> str:
    return parse_access_token_claims(token, settings).user_id

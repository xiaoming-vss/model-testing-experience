from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import ErrBadRequest, ErrUnauthorized

_BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(raw: str) -> str:
    raw_bytes = raw.encode("utf-8")
    if len(raw_bytes) > _BCRYPT_MAX_PASSWORD_BYTES:
        raise ErrBadRequest
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
    }
    return jwt.encode(payload, settings.jwt_key, algorithm="HS256")


def parse_access_token(token: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ErrUnauthorized from exc
    user_id = payload.get("userId")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ErrUnauthorized
    return user_id

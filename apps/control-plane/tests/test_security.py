from datetime import UTC, datetime

import pytest

from testing_agent.core import security
from testing_agent.core.errors import ErrBadRequest
from testing_agent.core.security import hash_password, verify_password


def test_hash_password_works_with_current_bcrypt_backend():
    hashed = hash_password("secret123")

    assert hashed.startswith("$2")
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_hash_password_rejects_bcrypt_overlong_password():
    with pytest.raises(type(ErrBadRequest)):
        hash_password("x" * 73)

    assert verify_password("x" * 73, "$2b$12$invalid-invalid-invalid-invalid-invalid") is False


def test_logins_at_the_same_time_get_distinct_tokens(monkeypatch):
    now = datetime.now(UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(security, "datetime", FrozenDatetime)
    first = security.create_access_token("same-user")
    second = security.create_access_token("same-user")
    assert first != second
    assert security.parse_access_token(first) == "same-user"
    assert security.parse_access_token(second) == "same-user"

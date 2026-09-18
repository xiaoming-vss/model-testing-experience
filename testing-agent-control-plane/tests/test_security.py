import pytest

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

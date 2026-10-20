"""Local account input rules shared by self-service and account administration."""

from testing_agent.core.errors import ErrPasswordTooLong, ErrPasswordTooShort

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_BYTES = 72


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ErrPasswordTooShort()
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ErrPasswordTooLong()

"""One UTC normalization rule for database and external timestamps."""

from datetime import UTC, datetime
from typing import overload


@overload
def as_utc(value: datetime) -> datetime: ...


@overload
def as_utc(value: None) -> None: ...


def as_utc(value: datetime | None) -> datetime | None:
    """Treat naive database values as UTC and normalize aware values to UTC."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def naive_utcnow() -> datetime:
    """Current UTC time without tzinfo, matching naive database timestamp columns."""
    return datetime.now(UTC).replace(tzinfo=None)

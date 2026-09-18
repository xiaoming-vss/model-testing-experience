"""Stable resource identity independent of a user's connection ID."""

from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

from testing_agent.core.errors import ErrBadRequest


def normalize_instance_url(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ErrBadRequest
        port = url.port
    except ValueError as exc:
        raise ErrBadRequest from exc
    host = url.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port and (url.scheme, port) not in (("http", 80), ("https", 443)):
        host += f":{port}"
    return urlunsplit((url.scheme.lower(), host, url.path.rstrip("/"), "", ""))


def instance_key(value: str) -> str:
    return sha256(normalize_instance_url(value).encode()).hexdigest()

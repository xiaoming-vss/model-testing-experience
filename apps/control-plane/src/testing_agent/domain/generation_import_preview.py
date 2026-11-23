"""Tamper-resistant, short-lived bindings for current-content import previews."""

import hashlib
import hmac
import re
import time
from dataclasses import asdict, dataclass

from testing_agent.domain.request_identity import request_signature

_TOKEN = re.compile(r"v1\.([0-9]{1,12})\.([0-9a-f]{64})\Z")


@dataclass(frozen=True)
class ImportPreviewBinding:
    actor_id: str
    requirement_id: str
    kind: str
    stage: str
    candidate_id: str
    snapshot_id: str
    current_token: str
    content_hash: str
    full_lineage_hash: str
    target_id: str
    target_fingerprint: str


def _signature(binding: ImportPreviewBinding, expires_at: int, secret: str) -> str:
    key = secret.encode("utf-8")
    if len(key) < 32:
        raise ValueError("preview signing key must contain at least 32 bytes")
    if any(not value for name, value in asdict(binding).items() if name != "target_id"):
        raise ValueError("preview binding is incomplete")
    payload = request_signature(
        "generation-current-import-preview-v1", {**asdict(binding), "expiresAt": expires_at}
    ).encode("ascii")
    derived = hmac.new(key, b"generation-current-import-preview-v1", hashlib.sha256).digest()
    return hmac.new(derived, payload, hashlib.sha256).hexdigest()


def issue_import_preview_token(
    binding: ImportPreviewBinding, *, secret: str, now: int | None = None, ttl_seconds: int = 600
) -> str:
    """Bind a preview to an actor, exact current chain and locked target state."""
    if not 1 <= ttl_seconds <= 3600:
        raise ValueError("preview lifetime must be between 1 and 3600 seconds")
    expires_at = (int(time.time()) if now is None else now) + ttl_seconds
    return f"v1.{expires_at}.{_signature(binding, expires_at, secret)}"


def validate_import_preview_token(
    token: str, binding: ImportPreviewBinding, *, secret: str, now: int | None = None
) -> bool:
    """Reject expiry, tampering or any change to actor, source or target state."""
    match = _TOKEN.fullmatch(token)
    if match is None:
        return False
    expires_at = int(match.group(1))
    if expires_at <= (int(time.time()) if now is None else now):
        return False
    return hmac.compare_digest(match.group(2), _signature(binding, expires_at, secret))

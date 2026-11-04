"""Stable fingerprints for user-supplied AI dispatch inputs."""

import hashlib
import json
from typing import Any

from testing_agent.core.errors import ErrBadRequest


def request_signature(kind: str, payload: dict[str, Any]) -> str:
    try:
        data = json.dumps(
            {"kind": kind, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ErrBadRequest() from exc
    return hashlib.sha256(data).hexdigest()

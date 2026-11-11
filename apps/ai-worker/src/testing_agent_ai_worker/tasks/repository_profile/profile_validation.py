"""Static schema validation for repository profile output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA = json.loads(Path(__file__).with_name("profile_schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def schema_errors(value: Any) -> list[dict[str, str]]:
    """Return bounded, model-friendly schema errors."""

    errors = []
    for error in sorted(VALIDATOR.iter_errors(value), key=lambda item: list(item.path)):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path
        )
        errors.append({"path": path, "code": error.validator, "message": error.message})
    return errors[:20]

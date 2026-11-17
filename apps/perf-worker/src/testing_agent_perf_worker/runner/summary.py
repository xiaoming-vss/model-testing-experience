"""k6 summary parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_summary(path: Path, max_summary_mb: int) -> tuple[dict[str, Any] | None, bool]:
    """Return a compact summary and whether the summary was missing."""

    if not path.is_file():
        return None, True
    try:
        if path.stat().st_size > max_summary_mb * 1024 * 1024:
            return None, True
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, True
    if not isinstance(raw, dict):
        return None, True
    return compact_summary(raw), False


def compact_summary(raw: dict[str, Any]) -> dict[str, Any]:
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict):
        return raw
    compact: dict[str, Any] = {}
    for name, value in metrics.items():
        if not isinstance(value, dict):
            continue
        item: dict[str, Any] = {}
        for key in ("type", "values", "thresholds"):
            if key in value:
                item[key] = value[key]
        compact[name] = item
    return {"metrics": compact}

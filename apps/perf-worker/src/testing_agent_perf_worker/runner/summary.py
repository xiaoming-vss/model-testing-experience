"""k6 summary parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_summary(path: Path, max_summary_mb: int) -> tuple[dict[str, Any] | None, bool, str]:
    """Return a compact summary, whether it is unusable, and why it could not be used.

    The reason is empty when k6 simply did not write the file; it names the limit or
    the defect otherwise, so a user can tell a missing summary from a broken one.
    """

    if not path.is_file():
        return None, True, ""
    try:
        if path.stat().st_size > max_summary_mb * 1024 * 1024:
            return None, True, f"k6 摘要超过 {max_summary_mb}MB 上限，已忽略"
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, True, "k6 摘要不是合法 JSON，已忽略"
    except OSError:
        return None, True, "k6 摘要无法读取，已忽略"
    if not isinstance(raw, dict):
        return None, True, "k6 摘要不是 JSON 对象，已忽略"
    return compact_summary(raw), False, ""


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

"""Structured unresolved YAML fields; independent of AI evidence or trace files."""

from __future__ import annotations

FIELDS = {"keyword", "locatorType", "locatorValue", "operationValue", "comparator"}
KEYS = {"fields", "operation", "target", "value", "reason"}


def validate_missing(step: dict) -> set[str]:
    entries = step.get("missingFields", [])
    if not isinstance(entries, list):
        raise ValueError("missingFields must be an array")
    pending = set()
    for index, entry in enumerate(entries, 1):
        prefix = f"missingFields[{index}]"
        if not isinstance(entry, dict) or set(entry) != KEYS:
            raise ValueError(
                f"{prefix} requires exactly fields, operation, target, value, reason"
            )
        fields = entry["fields"]
        if not isinstance(fields, list) or not all(
            isinstance(v, str) and v in FIELDS for v in fields
        ):
            raise ValueError(f"{prefix}.fields names unsupported fields")
        if len(set(fields)) != len(fields) or pending.intersection(fields):
            raise ValueError(f"{prefix} duplicates a missing field")
        for key in ("operation", "target", "reason"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                raise ValueError(f"{prefix}.{key} must describe the missing content")
        if entry["value"] is not None and not isinstance(
            entry["value"], (str, int, float, bool)
        ):
            raise ValueError(f"{prefix}.value must be a scalar or null")
        if "operationValue" in fields and step.get("keyword") in {
            "assert_visible",
            "assert_hidden",
            "sleep",
        }:
            raise ValueError(
                f"{prefix}: operationValue is milliseconds, not a business expected value; "
                "supply a wait duration and implement the business assertion separately"
            )
        for field in fields:
            if field not in step or step[field] is not None:
                raise ValueError(
                    f"{prefix}: {field} must be explicitly null; remove resolved entries"
                )
        pending.update(fields)
    return pending

#!/usr/bin/env python3
"""Validate a requirement review report (requires jsonschema)."""

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"invalid JSON number: {value}")


def check_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for child in value.values():
            check_finite(child)
    elif isinstance(value, list):
        for child in value:
            check_finite(child)


def sub_ids(values, available, label, errors):
    missing = sorted({value for value in values if value not in available})
    if missing:
        errors.append(f"{label}: unknown id(s) {missing}")


def validate(artifact, schema):
    errors = []
    for error in sorted(
        Draft202012Validator(schema).iter_errors(artifact),
        key=lambda item: [str(part) for part in item.absolute_path],
    ):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"schema {path}: {error.message}")
    if errors:
        return errors

    issue_ids = set()
    has_blocker = False
    has_major = False
    for issue in artifact["issues"]:
        issue_id = issue["id"]
        if issue_id in issue_ids:
            errors.append(f"duplicate issue id: {issue_id}")
        issue_ids.add(issue_id)
        severity = issue["severity"]
        if severity == "blocker":
            has_blocker = True
            if not str(issue.get("failureMode") or "").strip():
                errors.append(f"{issue_id}: blocker requires failureMode")
        elif severity == "major":
            has_major = True
        if severity in {"blocker", "major"} and not any(
            str(item.get("quote") or "").strip() for item in issue["evidence"]
        ):
            errors.append(f"{issue_id}: {severity} requires evidence with non-empty quote")

    expected = "blocked" if has_blocker else "needs_clarification" if has_major else "passed"
    if artifact["reviewStatus"] != expected:
        errors.append(
            f"reviewStatus must be {expected}, got {artifact['reviewStatus']}"
        )

    coverage = artifact["coverage"]
    for item in coverage["qualityCharacteristics"]:
        sub_ids(item["issueIds"], issue_ids, "coverage.qualityCharacteristics.issueIds", errors)
        if item["status"] == "fail" and not item["issueIds"]:
            errors.append(
                f"coverage.qualityCharacteristics: {item['name']} fail requires issueIds"
            )
        if item["status"] == "pass" and item["issueIds"]:
            errors.append(
                f"coverage.qualityCharacteristics: {item['name']} pass must not reference issues"
            )
    for item in coverage["smells"]:
        sub_ids([item["issueId"]], issue_ids, "coverage.smells.issueId", errors)
    for item in coverage["traceability"]:
        issue_id = str(item.get("issueId") or "").strip()
        if item["status"] == "fail":
            if not issue_id:
                errors.append("coverage.traceability: fail requires issueId")
            else:
                sub_ids([issue_id], issue_ids, "coverage.traceability.issueId", errors)
        elif issue_id:
            errors.append("coverage.traceability: pass must not reference an issue")
    return errors


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <review.json>", file=sys.stderr)
        return 2
    schema_path = (
        Path(__file__).resolve().parent.parent / "references/output.schema.json"
    )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        artifact = json.loads(
            Path(sys.argv[1]).read_text(encoding="utf-8"),
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
        )
        check_finite(artifact)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    errors = validate(artifact, schema)
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Check the skill's input, output, and references between them."""

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

REFERENCES = Path(__file__).resolve().parents[1] / "references"


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return Path(path).read_text(encoding="utf-8")


def load_document(path, kind):
    document = json.loads(read_json(path), object_pairs_hook=reject_duplicate_keys)
    schema = json.loads(read_json(REFERENCES / f"{kind}.schema.json"))
    try:
        Draft202012Validator(schema).validate(document)
    except ValidationError as exc:
        location = ".".join(map(str, exc.absolute_path)) or "<root>"
        raise ValueError(f"{kind} {location}: {exc.message}") from exc
    return document


def index_unique(values, key, description):
    index = {}
    for value in values:
        identity = key(value)
        if identity in index:
            raise ValueError(f"duplicate {description}: {identity}")
        index[identity] = value
    return index


EVIDENCE_FIELDS = {"precondition": "preconditions", "step": "steps"}


def evidence_positions(case):
    positions = {}
    for kind, field in EVIDENCE_FIELDS.items():
        indexed = index_unique(case[field], lambda entry: entry["position"], f"{field} position")
        if case["contentScope"] == "full_case" and set(indexed) != set(range(1, len(indexed) + 1)):
            raise ValueError(
                f"{case['caseId']}: full case must include consecutive {field} positions"
            )
        positions[kind] = indexed
    return positions


def validate_references(source, result):
    for field in ("requirementId", "materialSnapshotId", "impactResultId", "batchId"):
        if result[field] != source[field]:
            raise ValueError(f"output {field} does not match the input")
    if result["impactId"] != source["impact"]["impactId"]:
        raise ValueError("output impactId does not match the input")

    cases = index_unique(source["candidateCases"], lambda case: case["caseId"], "candidate case ID")
    findings = index_unique(
        result["caseFindings"], lambda finding: finding["caseId"], "finding case ID"
    )
    missing = cases.keys() - findings.keys()
    unknown = findings.keys() - cases.keys()
    if missing or unknown:
        raise ValueError(
            "case findings must match the batch: "
            f"missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    points = result.get("supplementalPoints")
    if points is None:
        index_unique(result["supplementalScenarios"], lambda item: item["scenarioId"], "scenario ID")
    else:
        index_unique(points, lambda item: item["pointId"], "supplemental point ID")

    for case_id, case in cases.items():
        finding = findings[case_id]
        positions = evidence_positions(case)
        if finding["caseSnapshotId"] != case["caseSnapshotId"]:
            raise ValueError(f"{case_id}: finding references a different snapshot")
        for citation in finding["evidence"]:
            kind, position = citation["kind"], citation["position"]
            if position not in positions[kind]:
                raise ValueError(f"{case_id}: unknown {kind} position {position}")
        is_full_case = case["contentScope"] == "full_case"
        if finding["decision"] == "invalidate" and not is_full_case:
            raise ValueError(f"{case_id}: invalidation requires the full case")
        if finding["needsFullCase"] and is_full_case:
            raise ValueError(f"{case_id}: the full case was already supplied")


def main():
    if len(sys.argv) != 3:
        print("usage: validate.py <output.json> <input.json>", file=sys.stderr)
        return 2
    try:
        source = load_document(sys.argv[2], "input")
        result = load_document(sys.argv[1], "output")
        validate_references(source, result)
    except (OSError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print("validation passed (structure and references)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

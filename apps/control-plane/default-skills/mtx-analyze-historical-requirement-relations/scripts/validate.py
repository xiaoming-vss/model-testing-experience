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


def material_key(material):
    return material["requirementId"], material["materialSnapshotId"]


def historical_key(relation):
    return relation["historicalRequirementId"], relation["historicalMaterialSnapshotId"]


def material_items(material):
    return index_unique(material["items"], lambda item: item["itemId"], "material item ID")


def cited_items(index, ids, label):
    unknown = set(ids) - index.keys()
    if unknown:
        raise ValueError(f"{label}: unknown item IDs {sorted(unknown)}")
    return [index[item_id] for item_id in ids]


def validate_references(source, result):
    current = source["currentRequirement"]
    current_items = material_items(current)
    if material_key(result) != material_key(current):
        raise ValueError("result must reference the current requirement and material snapshot")

    history = index_unique(source["historicalRequirements"], material_key, "historical snapshot")
    if any(key[0] == current["requirementId"] for key in history):
        raise ValueError("historical requirements must differ from the current requirement")
    historical_items = {key: material_items(value) for key, value in history.items()}
    snapshot_keys = history.keys() | {material_key(current)}
    for relation in source["knownRelations"]:
        origin = (relation["fromRequirementId"], relation["fromMaterialSnapshotId"])
        target = (relation["toRequirementId"], relation["toMaterialSnapshotId"])
        if origin[0] == target[0] or {origin, target} - snapshot_keys:
            raise ValueError("known relation must link two supplied requirement snapshots")

    relations = index_unique(
        result["relations"], lambda relation: relation["relationId"], "relation ID"
    )
    index_unique(result["relations"], historical_key, "relation target")
    impacts = index_unique(
        (impact for relation in relations.values() for impact in relation["impacts"]),
        lambda impact: impact["impactId"],
        "impact ID",
    )
    questioned = set()
    for question in result["openQuestions"]:
        impact_id = question["impactId"]
        if impact_id is not None:
            if impact_id not in impacts:
                raise ValueError(f"question references unknown impact ID: {impact_id}")
            questioned.add(impact_id)

    for relation in relations.values():
        key = historical_key(relation)
        if key not in history:
            raise ValueError(f"unknown historical requirement or snapshot: {key}")
        for impact in relation["impacts"]:
            impact_id = impact["impactId"]
            new_items = cited_items(current_items, impact["currentItemIds"], f"{impact_id} current")
            old_items = cited_items(
                historical_items[key], impact["historicalItemIds"], f"{impact_id} historical"
            )
            if impact["reviewStatus"] == "proposed":
                if any(item["status"] != "confirmed" for item in new_items + old_items):
                    raise ValueError(f"{impact_id}: proposed impacts must cite confirmed items")
            elif impact_id not in questioned:
                raise ValueError(f"{impact_id}: unclear impact requires a linked question")


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

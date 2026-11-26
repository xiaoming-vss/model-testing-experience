"""Historical requirement JSON contract, mirrored in both backend applications."""

import json
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("历史需求 JSON 存在重复字段")
        result[name] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("历史需求 JSON 存在非标准数值")


@lru_cache(maxsize=4)
def _validator(schema_name: str) -> Draft202012Validator:
    path = Path(__file__).with_name("requirement_schemas")
    source = path / f"{schema_name}.schema.json"
    return Draft202012Validator(json.loads(source.read_text(encoding="utf-8")))


def parse_historical_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value, object_pairs_hook=_pairs, parse_constant=_constant)
    return value


def validate_historical_json(value: object, schema_name: str) -> dict[str, Any]:
    value = parse_historical_json(value)
    try:
        _validator(schema_name).validate(value)
    except ValidationError as exc:
        location = ".".join(map(str, exc.absolute_path)) or "<root>"
        raise ValueError(f"历史影响产物 {schema_name} 字段校验失败: {location}") from exc
    assert isinstance(value, dict)  # The schema requires an object.
    return value


def validate_historical_input(value: object) -> dict[str, Any]:
    payload = validate_historical_json(value, "historical-requirement-relations-input")
    _validate_input_refs(payload)
    return payload


def validate_historical_output(value: object, source: object) -> dict[str, Any]:
    payload = validate_historical_input(source)
    result = validate_historical_json(value, "historical-requirement-relations-output")
    _validate_output_refs(payload, result)
    return result


def _index_unique(
    values: Iterable[dict[str, Any]], key: Callable[[dict[str, Any]], Any], description: str
) -> dict[Any, dict[str, Any]]:
    index = {}
    for value in values:
        identity = key(value)
        if identity in index:
            raise ValueError(f"duplicate {description}: {identity}")
        index[identity] = value
    return index


def material_key(material: dict[str, Any]) -> tuple[str, str]:
    return material["requirementId"], material["materialSnapshotId"]


def historical_key(relation: dict[str, Any]) -> tuple[str, str]:
    return relation["historicalRequirementId"], relation["historicalMaterialSnapshotId"]


def material_items(material: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _index_unique(material["items"], lambda item: item["itemId"], "material item ID")


def cited_items(
    index: dict[str, dict[str, Any]], ids: list[str], label: str
) -> list[dict[str, Any]]:
    unknown = set(ids) - index.keys()
    if unknown:
        raise ValueError(f"{label}: unknown item IDs {sorted(unknown)}")
    return [index[item_id] for item_id in ids]


def _validate_input_refs(source: dict[str, Any]) -> None:
    current = source["currentRequirement"]
    material_items(current)
    history = _index_unique(source["historicalRequirements"], material_key, "historical snapshot")
    if any(key[0] == current["requirementId"] for key in history):
        raise ValueError("historical requirements must differ from the current requirement")
    for value in history.values():
        material_items(value)
    snapshot_keys = history.keys() | {material_key(current)}
    for relation in source["knownRelations"]:
        origin = (relation["fromRequirementId"], relation["fromMaterialSnapshotId"])
        target = (relation["toRequirementId"], relation["toMaterialSnapshotId"])
        if origin[0] == target[0] or {origin, target} - snapshot_keys:
            raise ValueError("known relation must link two supplied requirement snapshots")


def _validate_output_refs(source: dict[str, Any], result: dict[str, Any]) -> None:
    current = source["currentRequirement"]
    current_items = material_items(current)
    if material_key(result) != material_key(current):
        raise ValueError("result must reference the current requirement and material snapshot")

    historical_items = {
        material_key(value): material_items(value) for value in source["historicalRequirements"]
    }
    relations = _index_unique(
        result["relations"], lambda relation: relation["relationId"], "relation ID"
    )
    _index_unique(result["relations"], historical_key, "relation target")
    impacts = _index_unique(
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
        if key not in historical_items:
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

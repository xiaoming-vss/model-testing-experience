"""Read YAML/JSON import envelopes shared by test asset importers."""

from typing import Any

import yaml


def parse_import_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        data = yaml.safe_load(payload) if payload.strip() else {}
        if isinstance(data, dict):
            return data
        return {"items": data or []}
    return {"items": payload or []}


async def read_import_payload(payload: Any = None, file: Any = None) -> dict[str, Any]:
    if file is not None:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
        return parse_import_payload(text)
    return parse_import_payload(payload)


def import_items(payload: Any, *keys: str) -> list[Any]:
    data = parse_import_payload(payload)
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    if isinstance(data.get("items"), list):
        return data["items"]
    return []

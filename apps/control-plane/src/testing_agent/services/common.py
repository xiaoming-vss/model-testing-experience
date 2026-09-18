from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def dump(schema: type[BaseModel], obj: Any) -> dict[str, Any]:
    return schema.model_validate(obj).model_dump(by_alias=True, mode="json")


def list_payload(items: list[Any]) -> dict[str, Any]:
    return paged_payload(items, len(items))


def paged_payload(items: list[Any], total: int) -> dict[str, Any]:
    """分页列表信封：total 是满足条件的总条数，而不是本页条数。"""
    return {"total": total, "items": items}


def apply_patch(obj: Any, body: dict[str, Any], allowed: set[str]) -> None:
    for key, value in body.items():
        snake_key = "".join(
            [f"_{char.lower()}" if char.isupper() else char for char in key]
        ).lstrip("_")
        if snake_key in allowed:
            setattr(obj, snake_key, value)

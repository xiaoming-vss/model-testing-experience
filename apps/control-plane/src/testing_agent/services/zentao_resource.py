"""Shared validation and error truncation for Zentao resource bindings."""


def parse_zentao_remote_id(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValueError("禅道资源ID不能为空")
    try:
        remote_id = int(text)
    except ValueError as exc:
        raise ValueError("禅道资源ID必须为数字") from exc
    if remote_id <= 0:
        raise ValueError("禅道资源ID必须大于0")
    return remote_id


def truncate_error(message: str, limit: int = 500) -> str:
    text = str(message or "")
    return text if len(text) <= limit else text[:limit]

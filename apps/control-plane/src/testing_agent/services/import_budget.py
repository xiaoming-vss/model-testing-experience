"""Bounded parsing for untrusted asset uploads; no database or remote operations."""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache
from typing import Any

import yaml

from testing_agent.core.errors import AppError
from testing_agent.core.import_limits import ImportLimits


def invalid(message: str) -> AppError:
    return AppError(400, message, 400)


def too_large(message: str) -> AppError:
    return AppError(413, message, 413)


def validate_structure(value: Any, limits: ImportLimits) -> None:
    pending = [(value, 0)]
    containers: set[int] = set()
    nodes = size = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > limits.max_nodes or depth > limits.max_depth:
            raise too_large("导入内容结构过于复杂")
        if isinstance(item, str):
            if len(item) > limits.max_field_chars:
                raise too_large("导入字段超过长度限制")
            size += len(item.encode("utf-8"))
        elif isinstance(item, (list, dict)):
            if id(item) in containers:
                raise invalid("导入内容不支持 YAML 别名或循环引用")
            containers.add(id(item))
            if isinstance(item, list):
                if len(item) > limits.max_items:
                    raise too_large("导入条数超过限制，请拆分文件")
                children = item
            else:
                children = [part for pair in item.items() for part in pair]
            if nodes + len(pending) + len(children) > limits.max_nodes:
                raise too_large("导入内容结构过于复杂")
            pending.extend((child, depth + 1) for child in children)
            size += len(children)
        else:
            size += len(str(item).encode("utf-8"))
        if size > limits.max_bytes:
            raise too_large("导入内容超过大小限制")


def parse_bounded(payload: Any, limits: ImportLimits) -> dict[str, Any]:
    if isinstance(payload, bytes):
        if len(payload) > limits.max_bytes:
            raise too_large("导入文件超过大小限制")
        try:
            payload = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise invalid("导入文件必须使用 UTF-8 编码") from None
    if isinstance(payload, str):
        if len(payload) > limits.max_bytes or len(payload.encode("utf-8")) > limits.max_bytes:
            raise too_large("导入内容超过大小限制")

        class BoundedLoader(yaml.SafeLoader):
            depth = 0
            nodes = 0

            def compose_node(self, parent, index):
                if self.check_event(yaml.AliasEvent):
                    raise invalid("导入内容不支持 YAML 别名，请展开后重试")
                self.depth += 1
                self.nodes += 1
                if self.depth > limits.max_depth or self.nodes > limits.max_nodes:
                    raise too_large("导入内容结构过于复杂")
                try:
                    return super().compose_node(parent, index)
                finally:
                    self.depth -= 1

        try:
            payload = yaml.load(payload, Loader=BoundedLoader) if payload.strip() else {}
        except (yaml.YAMLError, RecursionError, ValueError):
            raise invalid("导入内容不是有效的 YAML/JSON") from None
    validate_structure(payload, limits)
    if isinstance(payload, dict):
        return payload
    if payload is not None and not isinstance(payload, list):
        raise invalid("导入内容必须是对象或用例列表")
    return {"items": payload or []}


@lru_cache(maxsize=16)
def _slots(concurrent: int) -> threading.BoundedSemaphore:
    return threading.BoundedSemaphore(concurrent)


async def read_bounded(payload: Any, file: Any, limits: ImportLimits) -> dict[str, Any]:
    slots = _slots(limits.max_concurrent)
    if not slots.acquire(blocking=False):
        raise AppError(429, "导入处理繁忙，请稍后重试", 429)

    async def execute() -> dict[str, Any]:
        try:
            source = payload
            if file is not None:
                if (getattr(file, "size", None) or 0) > limits.max_bytes:
                    raise too_large("导入文件超过大小限制")
                data = bytearray()
                while len(data) <= limits.max_bytes:
                    chunk = await file.read(min(65536, limits.max_bytes + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                if len(data) > limits.max_bytes:
                    raise too_large("导入文件超过大小限制")
                source = bytes(data)
            return await asyncio.to_thread(parse_bounded, source, limits)
        finally:
            slots.release()

    # Cancellation of an HTTP request must not release capacity while its parser is still alive.
    task = asyncio.create_task(execute())
    task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.shield(task)

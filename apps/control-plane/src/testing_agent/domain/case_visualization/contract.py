"""Versioned visualization contract; synchronized into independently packaged applications."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

TASK_TYPE = "test_order_case_visualization"
SKILL_NAME = "mtx-analyze-case-visualization"
STATE_IDENTITY_MESSAGE = "状态保持必须引用同一已知状态"
MAX_INPUT_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 512 * 1024
SCHEMA = json.loads(Path(__file__).with_name("output.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def freeze_input(entry_id: str, content: dict[str, Any]) -> dict[str, Any]:
    """Preserve exact strings, empty fields and step indices; never reconstruct a pairing."""
    if not isinstance(content, dict) or set(content) != {"preconditions", "steps"}:
        raise ValueError("快照字段无效")
    preconditions, steps = content["preconditions"], content["steps"]
    if not isinstance(preconditions, list) or any(not isinstance(p, str) for p in preconditions):
        raise ValueError("前置条件必须为文本数组")
    if not isinstance(steps, list) or any(
        not isinstance(s, dict)
        or set(s) != {"action", "expected"}
        or any(not isinstance(s[k], str) for k in ("action", "expected"))
        for s in steps
    ):
        raise ValueError("操作与预期必须按快照配对")
    encoded = canonical(content).encode()
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError("用例内容超过图解输入上限，请使用文字模式")
    sources = []
    for index, text in enumerate(preconditions):
        if text.strip():
            sources.append({"id": f"p{index}", "field": "precondition", "index": index})
    for index, step in enumerate(steps):
        for field, prefix in (("action", "a"), ("expected", "e")):
            if step[field].strip():
                sources.append({"id": f"{prefix}{index}", "field": field, "index": index})
    if len(sources) > 1000:
        raise ValueError("用例来源数量超过图解上限，请使用文字模式")
    return {
        "executionEntryId": entry_id,
        "schemaVersion": "1.0",
        "snapshotHash": hashlib.sha256(b"case-content/1\0" + encoded).hexdigest(),
        "content": content,
        "sources": sources,
    }


def _unique(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped = {item["id"]: item for item in items}
    if len(mapped) != len(items):
        raise ValueError("图解标识重复")
    return mapped


def _depth(value: Any, level: int = 0) -> None:
    if level > 12:
        raise ValueError("图解嵌套超过上限")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, level + 1)


def validate_artifact(frozen: dict[str, Any], raw: str | dict[str, Any]) -> dict[str, Any]:
    """Validate shapes and provenance integrity; this does not certify semantic truth."""
    if isinstance(raw, str):
        if len(raw.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("图解结果超过大小上限")

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result = dict(items)
            if len(result) != len(items):
                raise ValueError("JSON 字段重复")
            return result

        value = json.loads(raw, object_pairs_hook=pairs)
    else:
        value = raw
    try:
        if len(canonical(value).encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("图解结果超过大小上限")
        _depth(value)
        if next(VALIDATOR.iter_errors(value), None) is not None:
            raise ValueError("图解结构不符合 1.0 协议")
    except (TypeError, RecursionError) as exc:
        raise ValueError("图解结构无效") from exc
    if value["executionEntryId"] != frozen["executionEntryId"]:
        raise ValueError("图解执行条目身份不匹配")
    if value["sources"] != frozen["sources"]:
        raise ValueError("图解必须原样使用平台来源目录")
    sources = _unique(value["sources"])
    entities = _unique(value["entities"])
    relations = _unique(value["relations"])
    assertions = _unique(value["assertions"])
    _unique(value["visuals"])

    def refs(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "sourceIds" or key.endswith("SourceIds"):
                    if any(s not in sources for s in child):
                        raise ValueError("图解包含非法来源引用")
                if key == "entityId" or key.endswith("EntityId"):
                    if child is not None and child not in entities:
                        raise ValueError("图解包含非法实体引用")
                if key == "entityIds" or key.endswith("EntityIds"):
                    if any(e not in entities for e in child):
                        raise ValueError("图解包含非法实体引用")
                refs(child)
        elif isinstance(item, list):
            for child in item:
                refs(child)

    refs(value)
    for entity in entities.values():
        bounds = entity.get("range")
        if bounds and bounds["start"] is not None and bounds["end"] is not None:
            if bounds["start"] > bounds["end"]:
                raise ValueError("区间起点不能晚于终点")
    for r in relations.values():
        if r["from"] not in entities or r["to"] not in entities:
            raise ValueError("关系端点不存在")
    for assertion in assertions.values():
        if not any(sources[s]["field"] == "expected" for s in assertion["sourceIds"]):
            raise ValueError("验证焦点必须有非空预期来源")
    if value["summary"]["text"] is not None and not value["summary"]["sourceIds"]:
        raise ValueError("摘要缺少依据")
    status, visuals = value["status"], value["visuals"]
    if (status == "unsupported") != (not visuals):
        raise ValueError("图解状态与图块数量不一致")
    if status in {"partial", "unsupported"} and not value["limitations"]:
        raise ValueError("未覆盖内容必须说明原因")
    if status == "partial" and any(not x["sourceIds"] for x in value["limitations"]):
        raise ValueError("部分覆盖的遗漏必须可以定位原文")
    for v in visuals:
        if (
            not set(v["relationIds"]) <= relations.keys()
            or not set(v["assertionIds"]) <= assertions.keys()
        ):
            raise ValueError("图块引用不存在")
        local = set(v["entityIds"])
        for rid in v["relationIds"]:
            if not {relations[rid]["from"], relations[rid]["to"]} <= local:
                raise ValueError("图块关系端点不闭合")
        for aid in v["assertionIds"]:
            if not set(assertions[aid]["entityIds"]) <= local:
                raise ValueError("图块断言实体不闭合")
        data = v["data"]

        def local_refs(item: Any, allowed: set[str]) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    if key == "entityId" or key.endswith("EntityId"):
                        if child is not None and child not in allowed:
                            raise ValueError("图块数据实体不闭合")
                    if key == "entityIds" or key.endswith("EntityIds"):
                        if not set(child) <= allowed:
                            raise ValueError("图块数据实体不闭合")
                    local_refs(child, allowed)
            elif isinstance(item, list):
                for child in item:
                    local_refs(child, allowed)

        local_refs(data, local)
        if v["kind"] == "interval":
            if not v["isSchematic"]:
                raise ValueError("1.0 区间仅支持非比例示意")
            segments = [s["entityId"] for s in data["orderedSegments"]]
            if len(segments) != len(set(segments)) or any(
                entities[e]["kind"] != "interval" for e in segments
            ):
                raise ValueError("区间实体无效或重复")
            if data["distinctOutputEntityIds"] and not data["distinctOutputSourceIds"]:
                raise ValueError("独立产出缺少依据")
        if v["kind"] == "state":
            action_id = data["actionEntityId"]
            if entities[action_id]["kind"] != "action":
                raise ValueError("状态图的操作必须引用操作实体")
            before, after = data["beforeEntityId"], data["afterEntityId"]
            if data["change"] == "unchanged":
                if before != after or before is None:
                    raise ValueError(STATE_IDENTITY_MESSAGE)
            elif data["change"] == "changed":
                if before is None or after is None or before == after:
                    raise ValueError("状态变化必须引用不同的前后状态")
            for entity_id in (before, after):
                if entity_id is not None and entities[entity_id]["kind"] != "state":
                    raise ValueError("状态图的前后状态必须引用状态实体")
        for note in v["notes"]:
            if any(sources[s]["field"] != "action" for s in note["sourceIds"]):
                raise ValueError("操作检查说明必须引用操作")
            for sid in note["sourceIds"]:
                index = sources[sid]["index"]
                if not frozen["content"]["steps"][index]["expected"].strip() and not any(
                    sid in x["sourceIds"] for x in value["limitations"]
                ):
                    raise ValueError("操作检查要求缺少预期时必须提示限制")
    return value

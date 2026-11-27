"""API 用例设计分批生成与合并校验。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.tasks.api_case_generate.design_contract import (
    DESIGN_SCHEMA_VERSION,
    validate_design_json,
    validate_design_object,
)
from testing_agent_ai_worker.tasks.output_repair import generate_validated

DESIGN_BATCH_SIZE = 5


def design_interface_batches(interfaces: list[str]) -> list[list[str]]:
    return [
        interfaces[index : index + DESIGN_BATCH_SIZE]
        for index in range(0, len(interfaces), DESIGN_BATCH_SIZE)
    ]


def _batch_payload(
    extraction: dict[str, Any],
    names: list[str],
    *,
    requirement: dict[str, Any],
    index: int,
    total: int,
    current_design: dict[str, Any] | None,
    revision_instruction: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "apiExtraction": {name: deepcopy(extraction[name]) for name in names},
        "requirement": deepcopy(requirement),
        "batch": {"index": index, "total": total, "interfaceNames": list(names)},
    }
    if current_design is not None:
        interfaces = current_design.get("interfaces")
        payload["currentDesign"] = {
            "schemaVersion": DESIGN_SCHEMA_VERSION,
            "interfaces": {
                name: deepcopy(interfaces[name])
                for name in names
                if isinstance(interfaces, dict) and name in interfaces
            },
        }
    if revision_instruction:
        payload["revisionInstruction"] = revision_instruction
    return payload


async def generate_design_batches(
    *,
    extraction: dict[str, Any],
    requirement: dict[str, Any],
    instruction: str,
    user_instruction: str,
    current_design: dict[str, Any] | None,
    revision_instruction: str,
    diagnostic_dir: Path | None,
    report: Callable[[dict[str, Any]], None],
    generate: Callable[[str, int, str], Awaitable[str] | str],
) -> dict[str, Any]:
    """按接口分批生成设计并合并；任一批失败则整体失败。"""

    names = list(extraction)
    batches = design_interface_batches(names)
    merged: dict[str, Any] = {}
    for index, batch in enumerate(batches, 1):
        payload = _batch_payload(
            extraction,
            batch,
            requirement=requirement,
            index=index,
            total=len(batches),
            current_design=current_design,
            revision_instruction=revision_instruction,
        )
        prompt = json.dumps(payload, ensure_ascii=False)
        if user_instruction.strip():
            prompt += "\n用户生成指令：\n" + user_instruction.strip()
        metadata = {
            "batchIndex": index,
            "batchCount": len(batches),
            "interfaceNames": list(batch),
            "completedInterfaces": len(merged),
        }

        def progress(event: dict[str, Any], metadata: dict[str, Any] = metadata) -> None:
            report({**event, **metadata})

        rules = (
            instruction + "\n本次仅设计 batch.interfaceNames 指定接口；"
            "返回本批完整设计 JSON，interfaces 不得多、不得少。"
            "不输出 Markdown、解释或其他 JSON 对象。"
        )
        progress({"stage": "api_design", "status": "generating"})
        try:
            raw = await generate_validated(
                stage="api_design",
                inputs=prompt,
                generate=lambda text, index=index, rules=rules: generate(text, index, rules),
                validate=lambda text, batch=batch: _validate_batch(text, extraction, batch),
                diagnostic_dir=(diagnostic_dir / f"batch-{index:03d}" if diagnostic_dir else None),
                report=progress,
                repair_instruction=(
                    "直接返回修复后的本批完整设计 JSON；不得增删本批接口，"
                    "不得输出 Markdown 或说明文字。"
                ),
            )
        except ValueError as exc:
            raise UserFacingError(
                f"接口用例设计第 {index}/{len(batches)} 批（接口 {', '.join(batch)}）失败：{exc}"
            ) from exc
        parsed = validate_design_json(raw, {name: extraction[name] for name in batch})
        merged.update(parsed["interfaces"])
        metadata["completedInterfaces"] = len(merged)
        progress(
            {
                "stage": "api_design",
                "status": "validated",
                "batchCaseCount": sum(len(parsed["interfaces"][name]["cases"]) for name in batch),
            }
        )
    result = validate_design_object(
        {"schemaVersion": DESIGN_SCHEMA_VERSION, "interfaces": merged},
        extraction,
    )
    ordered = {
        "schemaVersion": DESIGN_SCHEMA_VERSION,
        "interfaces": {name: result["interfaces"][name] for name in names},
    }
    report(
        {
            "stage": "api_design",
            "status": "merged",
            "batchCount": len(batches),
            "interfaceCount": len(names),
            "caseCount": sum(len(item["cases"]) for item in ordered["interfaces"].values()),
        }
    )
    return ordered


def _validate_batch(raw: str, extraction: dict[str, Any], batch: list[str]) -> dict[str, Any]:
    subset = {name: extraction[name] for name in batch}
    return validate_design_json(raw, subset)

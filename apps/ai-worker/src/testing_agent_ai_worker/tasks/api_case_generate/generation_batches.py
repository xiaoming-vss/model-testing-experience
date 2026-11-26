"""API 用例 YAML 分批生成、逐批对齐与合并校验。"""

from __future__ import annotations

import json
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.tasks.api_case_generate.design_contract import DESIGN_SCHEMA_VERSION
from testing_agent_ai_worker.tasks.api_case_generate.generation_contract import (
    dump_case_dicts,
    dump_cases,
    flatten_design,
    validate_generated_cases_json,
    validate_generated_cases_object,
)
from testing_agent_ai_worker.tasks.output_repair import generate_validated, parse_yaml

GENERATION_BATCH_SIZE = 10


def generation_case_batches(
    design: dict[str, Any],
) -> list[list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    rows = flatten_design(design)
    return [
        rows[index : index + GENERATION_BATCH_SIZE]
        for index in range(0, len(rows), GENERATION_BATCH_SIZE)
    ]


def _design_subset(
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    interfaces: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for name, interface, case in rows:
        item = interfaces.setdefault(
            name,
            {
                "method": interface["method"],
                "path": interface["path"],
                "cases": [],
                "uncovered": [],
            },
        )
        item["cases"].append(deepcopy(case))
    return {"schemaVersion": DESIGN_SCHEMA_VERSION, "interfaces": interfaces}


def _extraction_subset(
    extraction: dict[str, Any],
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    names = list(dict.fromkeys(name for name, _, _ in rows))
    return {name: deepcopy(extraction[name]) for name in names}


def _current_cases(
    current_yaml: str,
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]],
    start_order_no: int,
) -> list[dict[str, Any]]:
    if not current_yaml.strip():
        return []
    try:
        parsed = parse_yaml(current_yaml)
    except ValueError:
        return []
    cases = parsed.get("cases") if isinstance(parsed, dict) else None
    if not isinstance(cases, list):
        return []
    wanted = {start_order_no + index for index in range(len(rows))}
    return [
        deepcopy(case) for case in cases if isinstance(case, dict) and case.get("orderNo") in wanted
    ]


async def generate_cases_batches(
    *,
    extraction: dict[str, Any],
    design: dict[str, Any],
    requirement: dict[str, Any],
    instruction: str,
    user_instruction: str,
    current_yaml: str,
    revision_instruction: str,
    diagnostic_dir: Path | None,
    report: Callable[[dict[str, Any]], None],
    generate: Callable[[str, int, str], Awaitable[str] | str],
) -> str:
    """按设计顺序每 10 条一批生成 YAML，合并后再次全量校验。"""

    batches = generation_case_batches(design)
    merged_cases: list[Any] = []
    offset = 0
    for index, rows in enumerate(batches, 1):
        start_order_no = offset + 1
        payload: dict[str, Any] = {
            "apiExtraction": _extraction_subset(extraction, rows),
            "apiDesign": _design_subset(rows),
            "requirement": deepcopy(requirement),
            "batch": {
                "index": index,
                "total": len(batches),
                "caseIds": [case["id"] for _, _, case in rows],
                "startOrderNo": start_order_no,
            },
        }
        if revision_instruction:
            payload["currentYaml"] = dump_case_dicts(
                _current_cases(current_yaml, rows, start_order_no)
            )
            payload["revisionInstruction"] = revision_instruction
        prompt = json.dumps(payload, ensure_ascii=False)
        if user_instruction.strip():
            prompt += "\n用户生成指令：\n" + user_instruction.strip()
        metadata = {
            "batchIndex": index,
            "batchCount": len(batches),
            "caseIds": [case["id"] for _, _, case in rows],
            "startOrderNo": start_order_no,
            "endOrderNo": start_order_no + len(rows) - 1,
            "completedCases": offset,
        }

        def progress(event: dict[str, Any], metadata: dict[str, Any] = metadata) -> None:
            report({**event, **metadata})

        rules = (
            instruction + f"\n本次仅生成 batch.caseIds 指定的 {len(rows)} 条设计用例，"
            "一条设计对应一条 YAML，不多不少。"
            f"orderNo 使用全局序号，从 {start_order_no} 开始递增。"
            "保留设计补丁造成的非法或越界值，不得修复回合法值；"
            "只输出纯 YAML 对象，不输出 Markdown、解释或其他内容。"
        )
        progress({"stage": "api_case_generating", "status": "generating"})
        try:
            raw = await generate_validated(
                stage="api_case_generating",
                inputs=prompt,
                generate=lambda text, index=index, rules=rules: generate(text, index, rules),
                validate=lambda text, rows=rows, start_order_no=start_order_no: (
                    validate_generated_cases_json(
                        text,
                        _extraction_subset(extraction, rows),
                        _design_subset(rows),
                        start_order_no=start_order_no,
                    )
                ),
                diagnostic_dir=(diagnostic_dir / f"batch-{index:03d}" if diagnostic_dir else None),
                report=progress,
                repair_instruction=(
                    "直接返回修复后的本批完整 YAML；不得增删本批用例，"
                    "不得把设计要求的非法值修复回合法值，不得输出 Markdown 或说明文字。"
                ),
            )
        except ValueError as exc:
            raise UserFacingError(
                f"API 用例生成第 {index}/{len(batches)} 批"
                f"（用例 {start_order_no}-{start_order_no + len(rows) - 1}）失败：{exc}"
            ) from exc
        batch_cases = validate_generated_cases_json(
            raw,
            _extraction_subset(extraction, rows),
            _design_subset(rows),
            start_order_no=start_order_no,
        )
        merged_cases.extend(batch_cases.cases)
        offset += len(rows)
        metadata["completedCases"] = offset
        progress(
            {
                "stage": "api_case_generating",
                "status": "validated",
                "batchCaseCount": len(rows),
            }
        )
    merged = validate_generated_cases_object(
        {"cases": [case.model_dump(mode="json") for case in merged_cases]},
        extraction,
        design,
        start_order_no=1,
    )
    output = dump_cases(merged.cases)
    report(
        {
            "stage": "api_case_generating",
            "status": "merged",
            "batchCount": len(batches),
            "caseCount": len(merged.cases),
        }
    )
    return output

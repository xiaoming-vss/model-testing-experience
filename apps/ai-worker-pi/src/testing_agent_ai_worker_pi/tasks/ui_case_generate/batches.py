"""Bounded UI design batches with isolated repair and all-source merge validation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from ..output_repair import generate_validated
from .artifacts import DEFAULT_CAPABILITIES
from .design_contract import design_instruction, strict_json, validate_design_output


def build_batches(cases: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """One complete batch per module, preserving first-seen module/case order."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        groups.setdefault(str(case.get("module") or "未分组"), []).append(case)
    return list(groups.values())


def parse_response(raw: str) -> Any:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", text, flags=re.DOTALL)
    return strict_json(fenced.group(1).strip() if fenced else text)


async def generate_batches(
    *,
    body: dict[str, Any],
    generate: Callable,
    instruction: str,
    user_instruction: str,
    diagnostic_dir: Path,
    report: Callable,
) -> dict[str, Any]:
    cases = body["functionalCases"]
    batches = build_batches(cases)
    merged = []
    for index, batch in enumerate(batches, 1):
        ids = {case["caseId"] for case in batch}
        inputs = deepcopy(body)
        inputs.pop("outputPath", None)
        inputs["functionalCases"] = inputs["cases"] = batch
        if "currentArtifact" in inputs:
            inputs["currentArtifact"]["cases"] = [
                case for case in inputs["currentArtifact"]["cases"] if case["caseId"] in ids
            ]
        # Keep the approved graph intact; coverage is scoped to this batch only.
        inputs["surface"]["inspectionCoverage"] = [
            {**row, "caseIds": [cid for cid in row.get("caseIds", []) if cid in ids]}
            for row in inputs["surface"]["inspectionCoverage"]
            if ids.intersection(row.get("caseIds", []))
        ]
        inputs["batch"] = {"index": index, "total": len(batches), "caseIds": sorted(ids)}
        prompt = json.dumps(inputs, ensure_ascii=False)
        if user_instruction.strip():
            prompt += "\n用户生成指令：\n" + user_instruction.strip()
        metadata = dict(batch=index, batchCount=len(batches), completedCases=len(merged))

        def progress(event: dict) -> None:
            report({**event, **metadata})

        progress({"status": "generating"})
        raw = await generate_validated(
            stage="ui_design",
            inputs=prompt,
            generate=lambda text: generate(
                text,
                index,
                instruction
                + design_instruction()
                + "\n本次仅生成 batch.caseIds 指定用例。最终回复必须是本批完整 JSON 对象。"
                "不写产物文件，不返回 artifactPath/status 回执、说明或 Markdown。",
            ),
            validate=lambda text: validate_design_output(parse_response(text), batch),
            diagnostic_dir=diagnostic_dir / f"batch-{index:03d}",
            report=progress,
            repair_instruction="直接返回修复后的本批完整 JSON，禁止写文件或返回文件回执；不得增删本批用例。",
        )
        merged.extend(parse_response(raw)["cases"])
        metadata["completedCases"] = len(merged)
        progress({"status": "validated", "batchCaseCount": len(batch)})
    # Validate before reordering: never silently collapse duplicate identities.
    result = validate_design_output(
        dict(
            schemaVersion="ui_test_scenarios/2.0", capabilities=DEFAULT_CAPABILITIES, cases=merged
        ),
        cases,
    )
    by_id = {case["caseId"]: case for case in result["cases"]}
    result["cases"] = [by_id[case["caseId"]] for case in cases]
    report(dict(status="merged", batchCount=len(batches), completedCases=len(merged)))
    return result

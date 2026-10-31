"""Generate one YAML module at a time; publish only a validated complete merge."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import yaml

from ..output_repair import generate_validated, parse_yaml
from .batches import build_batches
from .completion import compile_case
from .missing_review import check_missing_semantics


class ExpandedDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump_yaml(rows: list[dict[str, Any]]) -> str:
    return yaml.dump(rows, Dumper=ExpandedDumper, allow_unicode=True, sort_keys=False)


def validate_module(
    raw: str,
    designs: list[dict[str, Any]],
    validate_yaml: Callable[[str], int],
    *,
    require_legacy: bool = False,
) -> list[dict[str, Any]]:
    rows = parse_yaml(raw)
    if require_legacy and isinstance(rows, list):
        issues = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            extra = set(row) - {"name", "enabled", "stepsJson", "orderNo"}
            steps = row.get("stepsJson")
            for step in steps if isinstance(steps, list) else []:
                if isinstance(step, dict):
                    extra.update({"dataBindings", "sourceRefs", "purpose"}.intersection(step))
                    if any(
                        "{{data." in str(step.get(key, ""))
                        for key in ("locatorValue", "operationValue")
                    ):
                        extra.add("data reference")
            if extra:
                issues.append(
                    dict(caseIndex=index, code="legacy_yaml_format", fields=sorted(extra))
                )
        if issues:
            raise ValueError(
                "使用原始用例/stepsJson/missingFields格式："
                + json.dumps(issues, ensure_ascii=False)
            )
    validate_yaml(raw)
    expected = [case["name"] for case in designs if case["coverage"] != "excluded"]
    actual = [case["name"] for case in rows]
    if actual != expected:
        raise ValueError(
            json.dumps(
                dict(
                    path="$",
                    code="case_coverage",
                    expected=expected,
                    actual=actual,
                    rule="按设计顺序输出每条未完全排除的用例，name逐字保留，不遗漏、不重复、不混入其他模块",
                ),
                ensure_ascii=False,
            )
        )
    for index, row in enumerate(rows):
        if not row["stepsJson"] and (require_legacy or not row.get("designConflicts")):
            raise ValueError(
                f"$[{index}].stepsJson: 保留用例必须有步骤；未知内容使用 missingFields"
            )
    return rows


async def generate_yaml_batches(
    *,
    body: dict[str, Any],
    generate: Callable,
    instruction: str,
    user_instruction: str,
    diagnostic_dir: Path,
    report: Callable,
    validate_yaml: Callable[[str], int],
    review: Callable | None = None,
    review_report: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    cases = body["functionalCases"]
    designs = {case["caseId"]: case for case in body["design"]["cases"]}
    ordered = [designs[case["caseId"]] for case in cases]
    retained = [case for case in ordered if case["coverage"] != "excluded"]
    current = {}
    if "currentArtifact" in body:
        rows = validate_module(body["currentArtifact"], ordered, validate_yaml)
        current = {case["caseId"]: row for case, row in zip(retained, rows, strict=True)}
    batches = build_batches(cases)
    results = {}
    review_inputs = []
    for index, batch in enumerate(batches, 1):
        ids = {case["caseId"] for case in batch}
        batch_designs = [designs[case["caseId"]] for case in batch]
        keep = [case for case in batch_designs if case["coverage"] != "excluded"]
        metadata = dict(
            batch=index,
            batchCount=len(batches),
            module=batch[0].get("module") or "未分组",
            completedCases=len(results),
        )

        def progress(event: dict) -> None:
            report({**event, **metadata})

        if not keep:
            progress(dict(status="excluded", batchCaseCount=0))
            continue
        inputs = deepcopy(body)
        inputs.pop("outputPath", None)
        inputs["functionalCases"] = inputs["cases"] = batch
        inputs["design"]["cases"] = batch_designs
        inputs["surface"]["inspectionCoverage"] = [
            {**row, "caseIds": [cid for cid in row.get("caseIds", []) if cid in ids]}
            for row in inputs["surface"]["inspectionCoverage"]
            if ids.intersection(row.get("caseIds", []))
        ]
        if "currentArtifact" in inputs:
            rows = [compile_case(current[case["caseId"]], for_validation=True) for case in keep]
            for number, row in enumerate(rows, 1):
                row["orderNo"] = number
            inputs["currentArtifact"] = dump_yaml(rows)
        inputs["batch"] = dict(
            index=index,
            total=len(batches),
            caseIds=[case["caseId"] for case in batch],
            expectedCaseNames=[case["name"] for case in keep],
        )
        # Give skill self-checks the exact reviewed design, not a model-reconstructed copy.
        batch_dir = diagnostic_dir / f"batch-{index:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        design_path = batch_dir / "reviewed-design.json"
        design_path.write_text(json.dumps(inputs["design"], ensure_ascii=False), encoding="utf-8")
        design_path.chmod(0o600)
        inputs["reviewedDesignPath"] = str(design_path.resolve())
        prompt = json.dumps(inputs, ensure_ascii=False)
        if user_instruction.strip():
            prompt += "\n用户生成指令：\n" + user_instruction.strip()

        def validate_candidate(text: str) -> None:
            validate_module(text, batch_designs, validate_yaml, require_legacy=True)

        progress(dict(status="generating"))
        raw = await generate_validated(
            stage="ui_yaml",
            inputs=prompt,
            generate=lambda text: generate(
                text,
                index,
                instruction
                + "\n使用平台原格式：用例只有 name/enabled/orderNo/stepsJson，步骤按原字段规则填写。"
                "未知内容仅在步骤内 missingFields 标记，不增加数据管理、引用或设计冲突元数据。"
                "本地自检使用 reviewedDesignPath 的已审核原始设计，逐项核对保留目标，不改写设计来通过校验。"
                "同一步同一根因只标记一项；数据缺口不能误标为控件不存在，也不重复追加准备提醒。"
                "只生成当前模块。直接返回完整 YAML list，即使只有一条也使用列表。"
                "返回前核对列表长度等于 batch.expectedCaseNames 长度，逐项校验 name 与 orderNo；不能只返回前半批或后半批。"
                "严格按 batch.expectedCaseNames 的名称和顺序逐条输出；本批用例 orderNo 从1连续递增，"
                "每条用例的 stepsJson.orderNo 也从1递增。保留第二阶段所有 included 操作和断言、"
                "前置条件、对象身份及观察时序。定位或数据未知时保留步骤和 missingFields。"
                "仅 coverage=excluded 的设计不输出。不要输出文件回执或 Markdown。",
            ),
            validate=validate_candidate,
            diagnostic_dir=diagnostic_dir / f"batch-{index:03d}",
            report=progress,
            repair_instruction="直接返回修复后的本模块完整 YAML list；保留有效步骤和已知值，未知字段使用 missingFields，不删除用例规避错误。先判断缺口能否补齐；不得将已有等待时间置空冒充业务期望，不得改用可见性掩盖值比较或本次执行的动态取值缺口。使用块式 YAML 并正确引用包含冒号或 XPath 的字符串。",
        )
        review_inputs.append((index, inputs, raw, keep))
        rows = parse_yaml(raw)
        results.update({case["caseId"]: row for case, row in zip(keep, rows, strict=True)})
        metadata["completedCases"] = len(results)
        progress(dict(status="validated", batchCaseCount=len(rows)))
    merged = [results[case["caseId"]] for case in retained]
    for index, row in enumerate(merged, 1):
        row["orderNo"] = index
    output = dump_yaml(merged)
    validate_module(output, ordered, validate_yaml, require_legacy=True)
    # Preserve the complete hard-validated draft before any advisory model call.
    candidate_path = diagnostic_dir / "candidate.yaml"
    diagnostic_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    candidate_path.write_text(output, encoding="utf-8")
    candidate_path.chmod(0o600)
    modules = []
    positions = {case["caseId"]: index for index, case in enumerate(retained, 1)}
    if review is not None:
        for batch_index, inputs, raw, keep in review_inputs:
            report(
                dict(
                    status="reviewing",
                    batch=batch_index,
                    batchCount=len(batches),
                    completedCases=len(merged),
                )
            )
            outcome = await check_missing_semantics(
                raw=raw,
                inputs=inputs,
                generate=lambda prompt, rules: review(prompt, batch_index, rules),
                diagnostic_dir=diagnostic_dir / f"batch-{batch_index:03d}" / "missing-review",
            )
            issues = []
            for issue in outcome["issues"]:
                case = keep[issue["caseIndex"] - 1]
                issues.append(
                    {
                        **issue,
                        "caseIndex": positions[case["caseId"]],
                        "caseId": case["caseId"],
                        "caseName": case["name"],
                    }
                )
            modules.append(
                {
                    **outcome,
                    "batch": batch_index,
                    "module": inputs["functionalCases"][0].get("module") or "未分组",
                    "issues": issues,
                }
            )
        if review_report is not None:
            review_report(
                {
                    "status": "incomplete"
                    if any(m["status"] == "incomplete" for m in modules)
                    else "completed",
                    "artifactSha256": sha256(output.encode("utf-8")).hexdigest(),
                    "modules": modules,
                }
            )
    report(
        dict(
            status="merged",
            batchCount=len(batches),
            completedCases=len(merged),
            excludedCases=len(cases) - len(merged),
        )
    )
    return output

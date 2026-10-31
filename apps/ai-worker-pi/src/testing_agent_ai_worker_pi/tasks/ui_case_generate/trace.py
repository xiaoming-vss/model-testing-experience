"""Check source coverage and prevent assertions from degrading during YAML binding."""

from __future__ import annotations

import json
from typing import Any

from .completion import VERSION, compile_case

OPERATIONS = {
    "navigate": {"open", "click"},
    "click": {"click"},
    "dblclick": {"dblclick"},
    "input": {"input"},
    "clear": {"clear"},
    "press": {"press"},
    "reload": {"reload"},
    "screenshot": {"screenshot"},
    "sleep": {"sleep"},
    "wait": {"wait_text", "assert_visible", "sleep"},
    "observe": {"assert_text", "assert_visible", "assert_url", "wait_text", "screenshot"},
}
ASSERTIONS = {
    "text_eq": {("assert_text", "eq")},
    "text_contains": {("assert_text", "contains"), ("wait_text", None)},
    "visible": {("assert_visible", None)},
    "absent": {("assert_hidden", None)},
    "url_eq": {("assert_url", "eq")},
    "url_contains": {("assert_url", "contains")},
}


def validate_trace(case: dict[str, Any], design: dict[str, Any]) -> None:
    if case.get("draftVersion") != VERSION:
        raise ValueError(f"{design['caseId']}: 需要 draftVersion: {VERSION} 和可追踪来源")
    compile_case(case, for_validation=True)
    sources = {}
    for step in design["steps"]:
        for kind, field, id_key in (
            ("action", "actions", "actionId"),
            ("expectation", "expectations", "expectationId"),
        ):
            for item in step[field]:
                sources[f"{kind}:{item[id_key]}"] = item
    required = {ref for ref, item in sources.items() if item["status"] == "included"}
    covered = set()
    issues = []

    def issue(path: str, message: str) -> None:
        issues.append(
            dict(path=path, caseId=design["caseId"], code="source_coverage", expected=message)
        )

    for index, conflict in enumerate(case.get("designConflicts", [])):
        for ref in conflict["sourceRefs"]:
            if ref not in required:
                issue(
                    f"$.designConflicts[{index}].sourceRefs", f"设计冲突引用未知或已排除目标: {ref}"
                )
            else:
                covered.add(ref)
    for index, step in enumerate(case["stepsJson"]):
        path = f"$.stepsJson[{index}]"
        refs = step.get("sourceRefs")
        purpose = step.get("purpose")
        if (
            not isinstance(refs, list)
            or not all(isinstance(r, str) for r in refs)
            or len(set(refs)) != len(refs)
        ):
            issue(path + ".sourceRefs", "sourceRefs 必须是无重复来源数组")
            continue
        if purpose not in {"business", "setup", "synchronization"}:
            issue(path + ".purpose", "purpose 必须是 business/setup/synchronization")
        if any(not entry.get("fields") for entry in step.get("missingFields", [])):
            issue(
                path + ".missingFields",
                "准备缺口放 dataRequirements，能力冲突放 designConflicts；不能用空fields代替断言",
            )
        if purpose == "business" and not refs:
            issue(path + ".sourceRefs", "业务步骤缺少 sourceRefs")
        if purpose != "business" and any(r.startswith("expectation:") for r in refs):
            issue(path + ".purpose", "业务断言不能降为准备或同步步骤")
        if purpose == "synchronization" and step["keyword"] not in {
            "wait_text",
            "assert_visible",
            "assert_hidden",
            "assert_text",
            "assert_url",
            "sleep",
        }:
            issue(
                path + ".purpose",
                "同步/辅助检查步骤只能等待或检查界面状态，操作步骤应标记为 business 或 setup",
            )
        if purpose == "business" and not step.get("enabled", False):
            issue(path + ".enabled", "不能禁用应保留的业务步骤")
        for ref in refs:
            if ref not in required:
                issue(path + ".sourceRefs", f"引用了未知、记录性或已排除目标 {ref}")
                continue
            if purpose != "business":
                continue
            item = sources[ref]
            if ref.startswith("expectation:"):
                if (step["keyword"], step.get("comparator")) not in ASSERTIONS.get(
                    item["assertion"], set()
                ):
                    issue(
                        path + ".keyword",
                        f"{ref}: {item['assertion']} 不能由 {step['keyword']} 替代；保留同等断言，确实无法实现则报告 designConflicts",
                    )
                else:
                    covered.add(ref)
            elif step["keyword"] in OPERATIONS.get(item["operation"], set()):
                # Coarse stage-two actions may expand into navigation/input/refresh/check
                # steps. Require a primary operation witness, not identical keywords on
                # every auxiliary step. Assertion references remain strictly typed.
                covered.add(ref)
    if required - covered:
        issue(
            "$.stepsJson",
            "未覆盖第二阶段保留目标（操作需要至少一个主操作步骤）: "
            + ", ".join(sorted(required - covered)),
        )
    if issues:
        raise ValueError(json.dumps(issues[:20], ensure_ascii=False))

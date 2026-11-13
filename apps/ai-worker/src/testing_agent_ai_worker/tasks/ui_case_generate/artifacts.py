"""Versioned UI stage artifacts. Protocol validation ships in each independent app."""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from typing import Any

from testing_agent_ai_worker.skill_names import UI_DESIGN_SKILL, UI_SURFACE_SKILL, UI_YAML_SKILL

UI_STAGES = ("ui_surface", "ui_design", "ui_yaml")
UI_FIELDS = {"ui_surface": "uiSurface", "ui_design": "uiDesign"}
UI_WORKFLOW_VERSION = "ui_three_stage/1.0"
UI_SKILLS = {
    "ui_surface": UI_SURFACE_SKILL,
    "ui_design": UI_DESIGN_SKILL,
    "ui_yaml": UI_YAML_SKILL,
}


def normalize(text: Any) -> str:
    text = re.sub(r"^\s*\d+(?:\.(?!\d)|[、．)])\s*", "", str(text))
    return "".join(
        c
        for c in text
        if not c.isspace() and (c in "-+/%<>=≤≥" or not unicodedata.category(c).startswith("P"))
    )


def object_value(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("阶段产物必须是 JSON 对象")
    return deepcopy(value)


def validate_surface(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    data = object_value(value)
    if data.get("schemaVersion") != "ui_test_surface/1.0" or not isinstance(data.get("app"), dict):
        raise ValueError("元素清单需要 ui_test_surface/1.0 和 app 对象")
    ids: set[str] = set()
    pages: set[str] = set()
    for key, identity in (
        ("pages", "pageId"),
        ("containers", "containerId"),
        ("controls", "controlId"),
        ("feedback", "feedbackId"),
        ("interactions", "interactionId"),
    ):
        rows = data.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"元素清单缺少 {key} 数组")
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get(identity), str)
                or not row[identity]
                or row[identity] in ids
            ):
                raise ValueError(f"{key} 存在缺失或重复标识")
            ids.add(row[identity])
            if key == "pages":
                pages.add(row[identity])
                if not row.get("route") or not row.get("componentFile"):
                    raise ValueError("页面缺少 route/componentFile")
            elif row.get("pageId") not in pages:
                raise ValueError(f"{key} 引用未知页面")
            if not re.fullmatch(r".+:\d+", str(row.get("sourceRef") or "")):
                raise ValueError(f"{key} 缺少 file:line 来源")
            for locator in row.get("locatorCandidates", []):
                if (
                    not isinstance(locator, dict)
                    or not locator.get("locatorValue")
                    or locator.get("evidenceType") not in {"source", "runtime"}
                ):
                    raise ValueError("定位候选缺少表达式或证据类型")
                if locator.get("locatorType") not in {
                    "css",
                    "xpath",
                    "role",
                    "text",
                    "placeholder",
                    "label",
                    "test_id",
                    "testid",
                }:
                    raise ValueError("定位类型不支持")
    if not isinstance(data.get("unknowns"), list) or not isinstance(
        data.get("inspectionCoverage"), list
    ):
        raise ValueError("元素清单需要 unknowns/inspectionCoverage 数组")
    covered = {cid for row in data["inspectionCoverage"] for cid in row.get("caseIds", [])}
    if covered != {case["caseId"] for case in cases}:
        raise ValueError("元素检查范围必须涵盖且只涵盖本次功能用例")
    return data


def validate_design(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    data = object_value(value)
    try:
        errors = _design_errors(data, cases=cases)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("UI 用例设计结构不合法") from exc
    if errors:
        raise ValueError("; ".join(errors[:20]))
    return data


DEFAULT_CAPABILITIES = {
    "operations": [
        "navigate",
        "click",
        "dblclick",
        "input",
        "clear",
        "press",
        "wait",
        "observe",
        "reload",
        "screenshot",
        "sleep",
    ],
    "assertions": [
        "visible",
        "text_eq",
        "text_contains",
        "url_eq",
        "url_contains",
        "absent",
    ],
}

# Designs approved before negative assertions were supported keep their declared profile.
LEGACY_DEFAULT_CAPABILITIES = {
    **DEFAULT_CAPABILITIES,
    "assertions": ["visible", "text_eq", "text_contains", "url_eq", "url_contains"],
}


def _design_errors(report, *, cases, surface=None, requirements=None, capabilities=None):
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    check(
        report.get("schemaVersion") == "ui_test_scenarios/2.0",
        "unsupported schemaVersion",
    )
    source = cases["cases"] if isinstance(cases, dict) else cases
    originals = {c["caseId"]: c for c in source}
    profile = report.get("capabilities", {})
    for name in ("operations", "assertions"):
        check(
            isinstance(profile.get(name), list)
            and all(isinstance(v, str) for v in profile.get(name, [])),
            f"missing capabilities.{name}",
        )
    expected_profiles = (
        [capabilities]
        if capabilities is not None
        else [DEFAULT_CAPABILITIES, LEGACY_DEFAULT_CAPABILITIES]
    )
    check(
        any(profile == expected for expected in expected_profiles),
        "capabilities differ from caller/platform profile",
    )
    designs = report.get("cases", [])
    check(isinstance(designs, list), "cases must be an array")
    if not isinstance(designs, list):
        return errors
    seen = set()
    forbidden = {
        "actionBindings",
        "observationBindings",
        "locatorType",
        "locatorValue",
        "dataPlan",
    }
    for case in designs:
        cid = case.get("caseId")
        check(cid in originals and cid not in seen, f"{cid}: unknown/duplicate case")
        seen.add(cid)
        if cid not in originals:
            continue
        original = originals[cid]
        check(case.get("sourceTitle") == original["title"], f"{cid}: source title changed")
        check(
            bool(case.get("name")) and bool(case.get("goal")),
            f"{cid}: name/goal required",
        )
        check(
            case.get("preconditions") == original["content"].get("preconditions", []),
            f"{cid}: original preconditions changed",
        )
        check(
            not forbidden.intersection(case),
            f"{cid}: design contains execution bindings",
        )
        steps = case.get("steps", [])
        check(
            len(steps) == len(original["content"]["steps"]),
            f"{cid}: source steps missing/extra",
        )
        ids = set()
        action_ids = set()
        statuses = []
        excluded_ids = set()
        excluded_actions = False
        for index, (step, src) in enumerate(
            zip(steps, original["content"]["steps"], strict=False), 1
        ):
            path = f"{cid} step {index}"
            check(
                step.get("sourceStepNo") == index and step.get("sourceAction") == src["action"],
                f"{path}: source action/order changed",
            )
            check(
                not forbidden.intersection(step),
                f"{path}: locator binding belongs to stage three",
            )
            action_text = normalize(src["action"])
            action_occupied = [False] * len(action_text)
            for action in step.get("actions", []):
                aid = action.get("actionId")
                check(
                    bool(aid) and aid not in action_ids,
                    f"{path}: missing/duplicate actionId",
                )
                action_ids.add(aid)
                check(
                    not forbidden.intersection(action),
                    f"{path}: locator binding belongs to stage three",
                )
                check(
                    bool(action.get("action"))
                    and isinstance(action.get("target"), str)
                    and "value" in action,
                    f"{path}: action/target/value required",
                )
                state = action.get("status")
                op = action.get("operation")
                check(state in ("included", "excluded"), f"{path}: invalid action status")
                statuses.append(state)
                if state == "included":
                    check(
                        op in profile.get("operations", []),
                        f"{path}: unsupported included operation {op}",
                    )
                else:
                    excluded_actions = True
                    check(
                        op not in profile.get("operations", []) and bool(action.get("reason")),
                        f"{path}: exclusion needs unsupported capability and reason",
                    )
                quote = action.get("sourceQuote", "")
                check(
                    bool(quote) and quote in src["action"],
                    f"{path}/{aid}: source action excerpt changed",
                )
                part = normalize(quote)
                offset = action_text.find(part) if part else -1
                while offset >= 0 and any(action_occupied[offset : offset + len(part)]):
                    offset = action_text.find(part, offset + 1)
                if offset < 0:
                    check(False, f"{path}/{aid}: overlapping action excerpt")
                else:
                    action_occupied[offset : offset + len(part)] = [True] * len(part)
            check(all(action_occupied), f"{path}: unaccounted source action")
            occupied = [False] * len(normalize(src["expected"]))
            for exp in step.get("expectations", []):
                eid = exp.get("expectationId")
                status = exp.get("status")
                assertion = exp.get("assertion")
                check(
                    bool(eid) and eid not in ids,
                    f"{path}: missing/duplicate expectation ID",
                )
                ids.add(eid)
                check(
                    status in ("included", "excluded", "bookkeeping"),
                    f"{path}/{eid}: invalid status",
                )
                check(
                    "value" in exp and isinstance(exp.get("target"), str),
                    f"{path}/{eid}: target/value required",
                )
                if status != "bookkeeping":
                    statuses.append(status)
                if status == "included":
                    check(
                        assertion in profile.get("assertions", []),
                        f"{path}/{eid}: unsupported assertion {assertion}",
                    )
                elif status == "excluded":
                    excluded_ids.add(eid)
                    check(
                        assertion not in profile.get("assertions", []) and bool(exp.get("reason")),
                        f"{path}/{eid}: exclusion needs unsupported capability and reason",
                    )
                else:
                    check(
                        assertion == "record" and bool(exp.get("reason")),
                        f"{path}/{eid}: bookkeeping requires recording reason",
                    )
                quote = exp.get("sourceQuote", "")
                check(
                    bool(quote) and quote in src["expected"],
                    f"{path}/{eid}: source excerpt changed",
                )
                text = normalize(src["expected"])
                part = normalize(quote)
                offset = text.find(part) if part else -1
                while offset >= 0 and any(occupied[offset : offset + len(part)]):
                    offset = text.find(part, offset + 1)
                if offset < 0:
                    check(False, f"{path}/{eid}: overlapping/invalid excerpt")
                else:
                    occupied[offset : offset + len(part)] = [True] * len(part)
            check(all(occupied), f"{path}: unaccounted expected text")
        core = case.get("coreExpectationIds", [])
        check(bool(core) and set(core) <= ids, f"{cid}: unresolved core expectations")
        coverage = (
            "full"
            if statuses and all(s == "included" for s in statuses)
            else "partial"
            if "included" in statuses
            else "excluded"
        )
        check(case.get("coverage") == coverage, f"{cid}: coverage must be {coverage}")
        check(
            isinstance(case.get("limitations"), list),
            f"{cid}: limitations must be an array",
        )
        if set(core) & excluded_ids or excluded_actions:
            check(
                bool(case.get("limitations")),
                f"{cid}: excluded core/action needs limitations",
            )
    check(seen == set(originals), "selected source cases missing from design")
    return errors

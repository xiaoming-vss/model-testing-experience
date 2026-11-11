#!/usr/bin/env python3
"""Lower an internal action/check plan to the existing platform YAML list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml


class EditableDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


from handoff import (
    HandoffError,
    check_step,
    effective_bundle,
    elements,
    evidenced_locators,
    locator,
    page_url,
    pointer,
    preflight,
    validate_handoff,
)
from validate_ui_case import validate_case


def compile_plan(bundle, plan):
    preflight(bundle)
    scenario = bundle["scenario"]
    observations = {b["observationIndex"]: b for b in scenario["observationBindings"]}
    case_plans = plan.get("cases", [plan])
    cases = []
    trace = {
        "schemaVersion": "ui_case_trace/1.0",
        "scenarioId": scenario["scenarioId"],
        "steps": [],
        "executionPrecheckRequired": scenario.get("executionPrecheckRequired", False),
    }
    for case_number, case_plan in enumerate(case_plans, 1):
        case = {
            "name": case_plan["name"],
            "enabled": True,
            "stepsJson": [],
            "orderNo": case_number,
        }

        def append(fields, row, name):
            number = len(case["stepsJson"]) + 1
            case["stepsJson"].append(
                dict(
                    orderNo=number,
                    stepName=name,
                    **fields,
                    continueOnFailure=False,
                    enabled=True,
                )
            )
            trace["steps"].append(
                dict(caseOrderNo=case_number, stepOrderNo=number, **row)
            )

        for instruction in case_plan["steps"]:
            if "observationIndex" in instruction:
                binding = observations[instruction["observationIndex"]]
                for number, check in enumerate(binding["checks"], 1):
                    fields = check_step(bundle, check)
                    row = {
                        "kind": "check",
                        "observations": [
                            {
                                "observationIndex": binding["observationIndex"],
                                "checkIndex": number,
                            }
                        ],
                        "afterActionIndex": instruction["afterActionIndex"],
                    }
                    for key in ["actionIndex", "beforeActionIndex"]:
                        if key in instruction:
                            row[key] = instruction[key]
                    item = elements(bundle)[check["targetId"]]
                    append(
                        fields,
                        row,
                        "核对 "
                        + (
                            item.get("semanticName")
                            or item.get("title")
                            or check["targetId"]
                        ),
                    )
            else:
                keyword = instruction["keyword"]
                row = {
                    k: instruction[k]
                    for k in [
                        "actionIndex",
                        "targetId",
                        "pageId",
                        "valueRef",
                        "purpose",
                        "functionCaseId",
                        "preconditionId",
                    ]
                    if k in instruction
                }
                row["kind"] = "setup" if "purpose" in instruction else "action"
                fields = {"keyword": keyword}
                if keyword == "open":
                    fields["operationValue"] = page_url(bundle, instruction["pageId"])
                else:
                    loc = locator(
                        bundle,
                        instruction["targetId"],
                        instruction.get("locatorIndex", 0),
                    )
                    fields.update(
                        locatorType=loc["locatorType"], locatorValue=loc["locatorValue"]
                    )
                    if keyword == "input":
                        fields["operationValue"] = str(
                            pointer(bundle, instruction["valueRef"])
                        )
                    elif keyword in {"press", "wait_text", "assert_visible"}:
                        fields["operationValue"] = str(instruction["operationValue"])
                append(
                    fields,
                    row,
                    instruction.get("stepName")
                    or f"{keyword} {instruction.get('targetId', instruction.get('pageId', ''))}",
                )
        cases.append(case)
    validate_handoff(cases, bundle, trace)
    for index, case in enumerate(cases, 1):
        validate_case(
            case,
            index,
            bundle["context"]["targetBaseUrl"],
            False,
            evidenced_locators(bundle),
        )
    return cases, trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--repair", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    if not args.bundle:
        if args.repair or args.trace:
            parser.error("--repair/--trace require a legacy --bundle")
        plan = json.loads(args.plan.read_text())
        cases = plan.get("cases", [plan]) if isinstance(plan, dict) else plan
        if not isinstance(cases, list) or not cases:
            parser.error("plan must contain nonempty cases")
        for index, case in enumerate(cases, 1):
            validate_case(case, index, "", False, allow_missing=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            yaml.dump(cases, Dumper=EditableDumper, allow_unicode=True, sort_keys=False)
        )
        print(f"OK: compiled {len(cases)} editable cases")
        return
    if not args.trace:
        parser.error("legacy --bundle requires --trace")
    try:
        bundle = effective_bundle(
            json.loads(args.bundle.read_text()),
            json.loads(args.repair.read_text()) if args.repair else None,
        )
        cases, trace = compile_plan(bundle, json.loads(args.plan.read_text()))
    except (HandoffError, KeyError, TypeError, ValueError) as exc:
        message = str(exc)
        print(
            message
            if message.startswith(("SCENARIO_BLOCKED:", "CLARIFICATION_REQUIRED:"))
            else "SCENARIO_BLOCKED: " + message,
            file=sys.stderr,
        )
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.trace.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.dump(cases, Dumper=EditableDumper, allow_unicode=True, sort_keys=False)
    )
    args.trace.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")
    print(f"OK: compiled {len(cases)} cases; YAML contract unchanged")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check an internal design-to-step account; never change candidate YAML.

This detects omitted targets and invalid references, not semantic equivalence.
The account is temporary generation evidence, not an import requirement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def required_targets(case: dict[str, Any]) -> dict[str, str]:
    targets = {}
    for step in case.get("steps", []):
        for collection, identity in (("actions", "actionId"), ("expectations", "expectationId")):
            for item in step.get(collection, []):
                if item.get("status") != "included":
                    continue
                key = item[identity]
                if key in targets:
                    raise ValueError(f"Repeated design target: {key}")
                targets[key] = collection
    return targets


def initialize_account(design: dict[str, Any]) -> dict[str, Any]:
    """Prepare empty target slots without claiming any candidate coverage."""
    cases = []
    for case in design["cases"]:
        if case["coverage"] == "excluded":
            continue
        required = required_targets(case)
        source = {item.get("actionId", item.get("expectationId")): item
                  for step in case.get("steps", [])
                  for group in ("actions", "expectations")
                  for item in step.get(group, [])}
        cases.append({"caseId": case["caseId"], "targets": [
            {"id": identity, "steps": [], "evidence": "",
             "source": {key: source[identity].get(key) for key in ("sourceQuote", "target", "value")}}
            for identity in required
        ]})
    return {"cases": cases}


def check_coverage(design: dict[str, Any], rows: list[dict[str, Any]], account: dict[str, Any]) -> None:
    cases = [case for case in design["cases"] if case["coverage"] != "excluded"]
    if [row["name"] for row in rows] != [case["name"] for case in cases]:
        raise ValueError("Candidate names/order differ from retained reviewed design")
    records = account.get("cases")
    if not isinstance(records, list) or [r.get("caseId") for r in records] != [c["caseId"] for c in cases]:
        raise ValueError("Account must contain every retained caseId in candidate order")
    for case, row, record in zip(cases, rows, records, strict=True):
        if row.get("enabled") is False:
            raise ValueError(f"{case['caseId']}: required case is disabled")
        required = required_targets(case)
        action_operations = {action["actionId"]: action.get("operation")
                             for source_step in case.get("steps", [])
                             for action in source_step.get("actions", [])}
        entries = record.get("targets")
        if not isinstance(entries, list):
            raise ValueError(f"{case['caseId']}: targets must be a list")
        ids = [entry.get("id") for entry in entries]
        if len(ids) != len(set(ids)) or set(ids) != set(required):
            missing = sorted(set(required) - set(ids))
            extra = sorted(set(ids) - set(required))
            raise ValueError(f"{case['caseId']}: missing={missing}, extra/excluded={extra}; each target once")
        steps = {step["orderNo"]: step for step in row["stepsJson"]}
        for entry in entries:
            identity = entry["id"]
            refs = entry.get("steps")
            if not isinstance(refs, list) or not refs or any(type(n) is not int or n not in steps for n in refs):
                raise ValueError(f"{identity}: reference actual candidate orderNo values")
            mapped = [steps[n] for n in refs]
            if any(s.get("enabled") is False for s in mapped):
                raise ValueError(f"{identity}: required coverage cannot use disabled steps")
            # Do not require identical keywords: a keyboard interaction can be
            # equivalent to a click. But a read-only assertion cannot perform it.
            if action_operations.get(identity) in {"navigate", "click", "dblclick", "input", "clear", "press", "reload"} and not any(
                s.get("keyword") in {"open", "click", "dblclick", "input", "clear", "press", "reload"}
                for s in mapped
            ):
                raise ValueError(f"{identity}: required action needs an interaction; observation/assertion alone cannot perform it")
            if required[identity] == "expectations" and not any(
                (str(s.get("keyword", "")).startswith("assert_") or s.get("keyword") == "wait_text")
                and s.get("continueOnFailure") is not True
                for s in mapped
            ):
                raise ValueError(f"{identity}: expected result needs an effective assertion, not just an action/saveTo or ignored failure")
            if not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
                raise ValueError(f"{identity}: explain the actual oracle/fields and scope; not only step names")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, nargs="?")
    parser.add_argument("--init", action="store_true", help="Create empty target slots from reviewed design")
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--account", required=True, type=Path)
    args = parser.parse_args()
    try:
        design = json.loads(args.design.read_text())
        if args.init:
            if args.account.exists():
                parser.exit(1, "Account already exists; preserve the existing work or choose a new path.\n")
            args.account.write_text(json.dumps(initialize_account(design), ensure_ascii=False, indent=2))
            print("Empty target account initialized; no coverage is claimed.")
            return
        if args.candidate is None:
            parser.error("candidate is required unless --init is used")
        check_coverage(design, yaml.safe_load(args.candidate.read_text()),
                       json.loads(args.account.read_text()))
    except (ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        parser.exit(1, f"Coverage account incomplete: {exc}\n")
    print("All included targets accounted for; verify semantic equivalence separately.")


if __name__ == "__main__":
    main()

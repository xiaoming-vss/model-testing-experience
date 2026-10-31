"""Scan stored UI cases for variable references before enabling pre-run checks.

升级后，`stepsJson` 里的 `{{名字}}` 会被运行前检查当作环境变量引用：不存在的变量
会拦住整轮运行。上线前用这个脚本扫一遍存量用例，列出需要补变量的位置。

    uv run --locked python scripts/scan_ui_case_variables.py
    uv run --locked python scripts/scan_ui_case_variables.py --json

有命中时退出码为 1，可以直接放进发版检查。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from sqlalchemy import select

from testing_agent.db.session import AsyncSessionLocal
from testing_agent.models.ui_test_case import UiTestCase

TOKEN = re.compile(r"\{\{(.*?)\}\}")
FIELDS = ("locatorValue", "operationValue", "saveTo.locatorValue")


def find_references(case: UiTestCase) -> list[dict[str, Any]]:
    steps = case.steps_json if isinstance(case.steps_json, list) else []
    findings: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        for field in FIELDS:
            if field == "saveTo.locatorValue":
                save_to = step.get("saveTo")
                if not isinstance(save_to, list):
                    continue
                for index, rule in enumerate(save_to, 1):
                    if isinstance(rule, dict) and isinstance(rule.get("locatorValue"), str):
                        for expression in _references(rule["locatorValue"]):
                            findings.append(
                                _entry(case, step, f"saveTo[{index}].locatorValue", expression)
                            )
                continue
            field_value = step.get(field)
            if isinstance(field_value, str):
                for expression in _references(field_value):
                    findings.append(_entry(case, step, field, expression))
    return findings


def _references(value: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in TOKEN.finditer(value)
        if match.group(1).strip() and not match.group(1).strip().startswith("$")
    ]


def _entry(case: UiTestCase, step: dict[str, Any], field: str, expression: str) -> dict[str, Any]:
    return {
        "caseId": case.case_id,
        "caseName": case.name,
        "orderNo": step.get("orderNo"),
        "stepName": step.get("stepName"),
        "field": field,
        "expression": expression,
    }


async def scan() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        cases = (await session.scalars(select(UiTestCase).order_by(UiTestCase.case_id))).all()
    return [finding for case in cases for finding in find_references(case)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是表格")
    args = parser.parse_args()

    findings = asyncio.run(scan())
    if args.json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("没有发现 UI 用例步骤中的变量引用。")
        for finding in findings:
            print(
                f"{finding['caseName']} ({finding['caseId']}) "
                f"步骤 {finding['orderNo']} {finding['stepName'] or '-'} "
                f"{finding['field']}: {finding['expression']}"
            )
        if findings:
            print(f"\n共 {len(findings)} 处引用，请确认对应环境变量已配置。")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

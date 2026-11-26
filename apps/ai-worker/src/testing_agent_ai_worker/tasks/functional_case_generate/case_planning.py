"""Match frozen functional targets before ordinary module generation."""

import json
from dataclasses import dataclass
from typing import Any

from testing_agent_ai_worker.agent.prompt import build_skill_message
from testing_agent_ai_worker.historical_test_case_artifacts import (
    validate_verification_run_input,
    validate_verification_run_output,
)
from testing_agent_ai_worker.skill_names import CASE_PLANNING_SKILL

from .validation import generate_validated, normalize_json


@dataclass(frozen=True)
class CasePlan:
    targets: list[dict[str, Any]]
    findings: list[dict[str, Any]]


def _history_inputs(history: dict) -> tuple[list[dict], list[dict]]:
    frozen = validate_verification_run_input(history["input"])
    verification = validate_verification_run_output(history["verification"], frozen)
    points = []
    findings = []
    for batch, output in zip(frozen["batches"], verification["batches"], strict=True):
        impact = batch["impact"]
        reference = {"impactId": impact["impactId"], "batchId": batch["batchId"]}
        effective = {}
        for round_name in ("firstPass", "fullCasePass"):
            result = output[round_name]
            if result is None:
                continue
            effective.update((finding["caseId"], finding) for finding in result["caseFindings"])
            for point in result.get("supplementalPoints", result.get("supplementalScenarios", [])):
                title = point.get("title")
                if title is None:
                    conditions = "；".join(point["preconditions"])
                    title = f"{conditions}。{point['action']} → {point['expected']}".lstrip("。")
                points.append(
                    {
                        "module": None,
                        "title": title,
                        "impact": impact,
                        "ref": {
                            **reference,
                            "stage": "historical_test_case_verification",
                            "round": round_name,
                            "pointId": point.get("pointId") or point["scenarioId"],
                        },
                    }
                )
        for item in effective.values():
            if item["decision"] in {"reuse", "modify", "invalidate"}:
                findings.append(
                    {
                        **item,
                        **reference,
                        "id": f"F{len(findings) + 1}",
                        "impact": impact,
                        "case": frozen["fullCases"][item["caseId"]],
                    }
                )
    return points, findings


def _materialize_plan(
    groups: list[dict], points: dict[str, dict], findings: dict[str, dict]
) -> CasePlan:
    targets = []
    seen = set()
    history = {
        key: {
            **{
                field: value
                for field, value in item.items()
                if field not in {"id", "case", "impact"}
            },
            "title": item["case"]["title"],
            "pointRefs": [],
        }
        for key, item in findings.items()
    }
    invalidated = {item["caseId"] for item in history.values() if item["decision"] == "invalidate"}
    for group in groups:
        ids = group["pointIds"]
        if (
            any(point_id not in points for point_id in ids)
            or seen.intersection(ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("生成规划包含未知或重复的测试点")
        seen.update(ids)
        sources = [points[point_id] for point_id in ids]
        primary = sources[0]
        if primary["module"] and primary["module"] != group["module"]:
            raise ValueError("生成规划必须沿用代表测试点的模块")
        if "impact" in primary and any("impact" not in point for point in sources):
            raise ValueError("功能测试点必须优先作为合并代表")
        refs = [point["ref"] for point in sources]
        finding_id = group["findingId"]
        if finding_id is not None:
            finding = history.get(finding_id)
            if (
                finding is None
                or finding["decision"] not in {"reuse", "modify"}
                or finding["caseId"] in invalidated
            ):
                raise ValueError("生成规划只能匹配已有的可复用或需修改结论")
            finding["pointRefs"].extend(refs)
            continue
        targets.append(
            {
                "id": ids[0],
                "module": group["module"],
                "title": primary["title"],
                "pointRefs": refs,
                "ruleImpacts": [point["impact"] for point in sources if "impact" in point],
            }
        )
    if seen != points.keys():
        raise ValueError("生成规划遗漏测试点")
    return CasePlan(targets, list(history.values()))


async def plan_case_generation(
    *,
    case_names_json: str,
    material: str,
    history: dict,
    factory,
    config_path: str | None,
    workspace: str | None,
    session_key: str,
) -> CasePlan:
    """Return checked module targets and the original historical conclusions."""
    supplemental, historical_findings = _history_inputs(history)
    functional = [
        {
            "module": point["module"],
            "title": point["name"],
            "ref": {"stage": "case_names", "pointId": point["id"]},
        }
        for point in json.loads(normalize_json(case_names_json))["testPoints"]
    ]
    points = {
        f"P{index}": point for index, point in enumerate([*functional, *supplemental], start=1)
    }
    findings = {item["id"]: item for item in historical_findings}
    payload = {
        "material": json.loads(material),
        "points": [
            {
                "id": key,
                "source": "historical" if "impact" in point else "functional",
                **{field: value for field, value in point.items() if field != "ref"},
            }
            for key, point in points.items()
        ],
        "findings": historical_findings,
    }
    result = None

    def validate_plan(output: dict) -> None:
        nonlocal result
        result = _materialize_plan(output["groups"], points, findings)

    if not points:
        return _materialize_plan([], points, findings)
    async with factory(config_path=config_path, workspace=workspace) as bot:
        await generate_validated(
            stage="case_planning",
            inputs=build_skill_message(
                skill_name=CASE_PLANNING_SKILL,
                body_text=json.dumps(payload, ensure_ascii=False),
                extra_instruction="按本次冻结输入匹配并返回生成规划 JSON。",
            ),
            generate=lambda prompt: bot.run(prompt, session_key=f"{session_key}:case_planning"),
            post_validate=validate_plan,
        )
    assert result is not None
    return result

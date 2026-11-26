"""Find and freeze project-owned historical cases by the adopted rule impacts."""

# transaction-bound: case reads and the candidate snapshot share the dispatch transaction.

import json
from collections import defaultdict
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.function_case_content import CaseContent
from testing_agent.domain.generation_chain import HISTORICAL_REQUIREMENT_STAGE
from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.historical_requirement_artifacts import validate_historical_json
from testing_agent.domain.historical_test_case_artifacts import (
    VERIFICATION_BATCH_INPUT,
    VERIFICATION_RUN_INPUT,
    validate_verification_run_input,
    verification_run_header,
)
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.services.generation_source_selection import ResolvedRunSources
from testing_agent.services.historical_requirement_inputs import historical_search_terms

CASES_PER_BATCH = 6
STEPS_PER_EXCERPT = 3


def _freeze_case(case: FunctionTestCase, requirement_id: str) -> dict[str, Any]:
    content = CaseContent.model_validate(case.content_json)
    full = {
        "caseId": case.case_id,
        "requirementId": requirement_id,
        "suiteId": case.suite_id,
        "module": case.module,
        "title": case.title,
        "contentScope": "full_case",
        "preconditions": [
            {"position": position, "text": text}
            for position, text in enumerate(content.preconditions, 1)
        ],
        "steps": [
            {"position": position, "action": step.action, "expected": step.expected}
            for position, step in enumerate(content.steps, 1)
        ],
    }
    encoded = json.dumps(full, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {**full, "caseSnapshotId": sha256(encoded).hexdigest()}


def _impact_source(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in (
            "impactId",
            "ruleEffect",
            "scope",
            "previousRule",
            "currentRule",
            "changeSummary",
        )
    }


def _excerpt(case: dict[str, Any], terms: set[str]) -> tuple[int, dict[str, Any]] | None:
    name = f"{case['module']} {case['title']}"
    header_score = len(terms & historical_search_terms(name))
    preconditions = " ".join(item["text"] for item in case["preconditions"])
    precondition_score = len(terms & historical_search_terms(preconditions))
    steps = [
        (len(terms & historical_search_terms(f"{step['action']} {step['expected']}")), step)
        for step in case["steps"]
    ]
    score = header_score + precondition_score + max((score for score, _ in steps), default=0)
    if not score:
        return None
    steps = sorted((item for item in steps if item[0]), key=lambda item: item[0], reverse=True)
    excerpt = sorted(
        (step for _, step in steps[:STEPS_PER_EXCERPT]), key=lambda step: step["position"]
    )
    return score, {**case, "contentScope": "matched_excerpt", "steps": excerpt}


async def build_historical_test_case_input(
    session: AsyncSession,
    *,
    project_id: str,
    requirement_id: str,
    sources: ResolvedRunSources,
) -> dict[str, Any]:
    """Use only adopted evidence and keep each matched case once per rule."""
    relation = next(
        (item for item in sources.selected_content if item.stage == HISTORICAL_REQUIREMENT_STAGE),
        None,
    )
    selected = next(
        (
            item
            for item in sources.manifest.selected_sources
            if item.stage == HISTORICAL_REQUIREMENT_STAGE
        ),
        None,
    )
    if relation is None or selected is None or selected.source_kind != "current":
        raise SourceClosureError("pending_upstream")
    try:
        artifact = validate_historical_json(
            relation.content, "historical-requirement-relations-output"
        )
        if artifact["requirementId"] != requirement_id:
            raise ValueError("关联结果属于其他需求")
        identity = {
            "requirementId": requirement_id,
            "materialSnapshotId": artifact["materialSnapshotId"],
            "impactResultId": selected.snapshot_id,
        }
        impacts = [
            (link["historicalRequirementId"], _impact_source(item))
            for link in artifact["relations"]
            for item in link["impacts"]
            if item["reviewStatus"] == "proposed" and item["ruleEffect"] != "still_applies"
        ]
        return await _build_batches(
            session, project_id=project_id, identity=identity, impacts=impacts
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise SourceClosureError("source_unknown") from exc


async def _build_batches(
    session: AsyncSession,
    *,
    project_id: str,
    identity: dict[str, Any],
    impacts: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    requirements_with_changes = {
        requirement_id
        for requirement_id, impact in impacts
        if impact["ruleEffect"] != "supplemented"
    }
    if requirements_with_changes:
        rows = await FunctionTestCaseRepository(session).list_active_for_historical_requirements(
            project_id, requirements_with_changes
        )
        for row, requirement_id in rows:
            candidates[requirement_id].append(_freeze_case(row, requirement_id))

    batches: list[dict[str, Any]] = []
    full_cases: dict[str, dict[str, Any]] = {}
    for requirement_id, impact in impacts:
        scope = (value for values in impact["scope"].values() for value in values)
        text = " ".join(
            [impact["previousRule"], impact["currentRule"] or "", impact["changeSummary"], *scope]
        )
        terms = historical_search_terms(text)
        matched = []
        # A pure addition uses an empty batch to propose coverage for the new scenario.
        cases = [] if impact["ruleEffect"] == "supplemented" else candidates[requirement_id]
        for case in cases:
            hit = _excerpt(case, terms)
            if hit is not None:
                matched.append(hit)
                full_cases[case["caseId"]] = case
        matched.sort(key=lambda item: item[0], reverse=True)
        for offset in range(0, max(len(matched), 1), CASES_PER_BATCH):
            batches.append(
                {
                    **verification_run_header(VERIFICATION_BATCH_INPUT, identity),
                    "batchId": f"batch-{len(batches) + 1}",
                    "impact": impact,
                    "candidateCases": [
                        case for _, case in matched[offset : offset + CASES_PER_BATCH]
                    ],
                }
            )
    return validate_verification_run_input(
        {
            **verification_run_header(VERIFICATION_RUN_INPUT, identity),
            "batches": batches,
            "fullCases": full_cases,
        }
    )

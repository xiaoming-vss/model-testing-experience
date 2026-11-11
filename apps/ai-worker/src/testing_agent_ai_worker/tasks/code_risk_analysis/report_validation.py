"""Strict, bounded validation for the formal code-risk report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from testing_agent_ai_worker.tasks.code_risk_analysis.workspace import CodeWorkspace
from testing_agent_ai_worker.tasks.output_repair import parse_yaml

SCHEMA = json.loads((Path(__file__).with_name("report_schema.json")).read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


class RiskReportValidationError(ValueError):
    """The model output is not a safe, self-consistent risk report."""

    def __init__(self, issues: list[dict[str, Any]]):
        self.issues = issues[:20]
        super().__init__(json.dumps(self.issues, ensure_ascii=False))


def _issue(path: str, code: str, expected: str, actual: Any = "") -> dict[str, Any]:
    return {"path": path, "code": code, "expected": expected, "actual": repr(actual)[:200]}


def _path_exists(workspace: CodeWorkspace, value: str) -> bool:
    if not value or value.startswith("/") or ".." in Path(value).parts:
        return False
    return any((repo.path / value).exists() for repo in workspace.repositories)


def validate_risk_report(
    raw: str,
    workspace: CodeWorkspace,
    *,
    expected_case_ids: set[str],
) -> dict[str, Any]:
    """Parse and validate a model report against deterministic task facts."""

    try:
        data = parse_yaml(raw)
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise RiskReportValidationError([_issue("$", "invalid_yaml", str(exc))]) from exc
    if not isinstance(data, dict):
        raise RiskReportValidationError([_issue("$", "invalid_type", "object", data)])
    errors = [
        _issue(".".join(str(part) for part in error.path) or "$", error.validator, error.message)
        for error in VALIDATOR.iter_errors(data)
    ]
    if errors:
        raise RiskReportValidationError(errors)

    known_repos = {repo.binding.repository_id: repo for repo in workspace.repositories}
    for index, item in enumerate(data.get("affectedCases", [])):
        case_id = item.get("caseId")
        if case_id not in expected_case_ids:
            errors.append(
                _issue(
                    f".affectedCases[{index}].caseId", "unknown_case_id", "input case ID", case_id
                )
            )
    for index, item in enumerate(data.get("risks", [])):
        location = item.get("location")
        if location and not _path_exists(workspace, location):
            errors.append(
                _issue(
                    f".risks[{index}].location", "unknown_path", "path in code workspace", location
                )
            )
        if not item.get("evidence"):
            errors.append(
                _issue(
                    f".risks[{index}].evidence", "missing_evidence", "at least one evidence item"
                )
            )

    for index, item in enumerate(data.get("repositories", [])):
        repository_id = item.get("repositoryId")
        expected = known_repos.get(repository_id)
        if expected is None:
            errors.append(
                _issue(
                    f".repositories[{index}].repositoryId",
                    "unknown_repository",
                    "input repository ID",
                    repository_id,
                )
            )
            continue
        for field, value in (
            ("branch", item.get("branch")),
            ("baselineCommit", item.get("baselineCommit")),
            ("headCommit", item.get("headCommit")),
        ):
            expected_value = {
                "branch": expected.binding.branch,
                "baselineCommit": expected.base_commit,
                "headCommit": expected.head_commit,
            }[field]
            if value != expected_value:
                errors.append(
                    _issue(
                        f".repositories[{index}].{field}", "fact_mismatch", expected_value, value
                    )
                )
    if errors:
        raise RiskReportValidationError(errors)
    return data

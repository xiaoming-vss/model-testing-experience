"""Strict repository profile output contract and unavailable-repository merging."""

from __future__ import annotations

import json
import math
from typing import Any

from testing_agent_ai_worker.tasks.repository_profile.workspace import (
    ProfileRepoWorkspace,
    ProfileWorkspace,
)

PROFILE_TOP_LEVEL_FIELDS = frozenset({"repositories", "overallSummary"})
PROFILE_REPOSITORY_FIELDS = frozenset(
    {
        "repositoryId",
        "pathWithNamespace",
        "role",
        "responsibilitySummary",
        "techStack",
        "keyPaths",
        "confidence",
        "evidence",
    }
)
PROFILE_ROLES = frozenset({"frontend", "backend", "fullstack", "infra", "test", "unknown"})
MAX_RESPONSIBILITY_CHARS = 120
MAX_OVERALL_SUMMARY_CHARS = 200


class ProfileContractError(RuntimeError):
    """The model returned content outside the repository profile contract."""


def validate_profile_output(
    raw_output: str,
    workspace: ProfileWorkspace,
    *,
    max_output_chars: int,
) -> dict[str, Any]:
    """Parse strict JSON, validate every readable repository, and merge unavailable ones."""
    text = str(raw_output or "").strip()
    if not text:
        raise ProfileContractError("模型输出为空")
    if len(text) > max_output_chars:
        raise ProfileContractError("模型输出超出长度限制")
    if text.startswith("```") or text.endswith("```"):
        raise ProfileContractError("模型输出不能包含 Markdown 代码块")
    if not text.startswith("{") or not text.endswith("}"):
        raise ProfileContractError("模型输出必须是单个 JSON 对象")
    try:
        data = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (TypeError, ValueError) as exc:
        raise ProfileContractError(f"模型输出不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileContractError("模型输出不是 JSON 对象")
    if set(data) != PROFILE_TOP_LEVEL_FIELDS:
        raise ProfileContractError("模型输出顶层字段与契约不一致")
    repositories = data.get("repositories")
    overall_summary = data.get("overallSummary")
    if not isinstance(repositories, list):
        raise ProfileContractError("repositories 必须是数组")
    if not isinstance(overall_summary, str) or not overall_summary.strip():
        raise ProfileContractError("overallSummary 不能为空")
    overall_summary = _one_line(overall_summary, "overallSummary")
    if len(overall_summary) > MAX_OVERALL_SUMMARY_CHARS:
        raise ProfileContractError("overallSummary 超出 200 字")

    readable = {repo.binding.repository_id: repo for repo in workspace.repositories}
    validated: dict[str, dict[str, Any]] = {}
    for item in repositories:
        if not isinstance(item, dict):
            raise ProfileContractError("repositories 条目必须是对象")
        if set(item) != PROFILE_REPOSITORY_FIELDS:
            raise ProfileContractError("仓库条目字段与契约不一致")
        repository_id = _non_empty_string(item.get("repositoryId"), "repositoryId")
        if repository_id in validated:
            raise ProfileContractError(f"仓库重复输出: {repository_id}")
        repo = readable.get(repository_id)
        if repo is None:
            raise ProfileContractError(f"输出了不可分析或不存在的仓库: {repository_id}")
        validated[repository_id] = _validate_repository(item, repo)

    expected = {repo.binding.repository_id for repo in workspace.repositories}
    missing = expected - set(validated)
    if missing:
        raise ProfileContractError(f"缺少仓库画像: {', '.join(sorted(missing))}")

    merged: list[dict[str, Any]] = []
    ordered = sorted(
        [*workspace.repositories, *workspace.unavailable],
        key=lambda item: item.order,
    )
    for item in ordered:
        if isinstance(item, ProfileRepoWorkspace):
            merged.append(validated[item.binding.repository_id])
        else:
            merged.append(_unavailable_profile(item.binding))
    return {"repositories": merged, "overallSummary": overall_summary}


def canonical_profile_json(profile: dict[str, Any]) -> str:
    return json.dumps(profile, ensure_ascii=False, indent=2)


def _validate_repository(item: dict[str, Any], repo: ProfileRepoWorkspace) -> dict[str, Any]:
    repository_id = _non_empty_string(item.get("repositoryId"), "repositoryId")
    path = _non_empty_string(item.get("pathWithNamespace"), "pathWithNamespace")
    expected_path = repo.binding.path_with_namespace or repo.binding.repository_id
    if path != expected_path:
        raise ProfileContractError(f"仓库路径与清单不一致: {repository_id}")
    role = item.get("role")
    if role not in PROFILE_ROLES:
        raise ProfileContractError(f"仓库角色不合法: {repository_id}")
    responsibility = _one_line(
        _non_empty_string(item.get("responsibilitySummary"), "responsibilitySummary"),
        f"{repository_id}.responsibilitySummary",
    )
    if len(responsibility) > MAX_RESPONSIBILITY_CHARS:
        raise ProfileContractError(f"仓库职责超出 120 字: {repository_id}")
    tech_stack = _string_list(item.get("techStack"), f"{repository_id}.techStack", max_items=5)
    key_paths = _string_list(item.get("keyPaths"), f"{repository_id}.keyPaths", max_items=5)
    evidence = _string_list(item.get("evidence"), f"{repository_id}.evidence", max_items=5)
    _validate_key_paths(repo, key_paths)
    confidence = item.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(float(confidence))
        or not 0 <= float(confidence) <= 1
    ):
        raise ProfileContractError(f"仓库置信度必须是 0 到 1: {repository_id}")
    if role == "unknown":
        if float(confidence) != 0:
            raise ProfileContractError(f"unknown 仓库置信度必须为 0: {repository_id}")
        if evidence:
            raise ProfileContractError(f"unknown 仓库 evidence 必须为空: {repository_id}")
    elif not evidence:
        raise ProfileContractError(f"仓库缺少 evidence: {repository_id}")
    return {
        "repositoryId": repository_id,
        "pathWithNamespace": path,
        "role": role,
        "responsibilitySummary": responsibility,
        "techStack": tech_stack,
        "keyPaths": key_paths,
        "confidence": float(confidence),
        "evidence": evidence,
    }


def _validate_key_paths(repo: ProfileRepoWorkspace, key_paths: list[str]) -> None:
    root = repo.path.resolve()
    for value in key_paths:
        if value.startswith(("/", "\\")) or "\\" in value:
            raise ProfileContractError(f"keyPaths 必须是仓库相对路径: {value}")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ProfileContractError(f"keyPaths 不能包含空段或 ..: {value}")
        candidate = (repo.path / value).resolve()
        if root != candidate and root not in candidate.parents:
            raise ProfileContractError(f"keyPaths 越出仓库目录: {value}")
        if not candidate.exists():
            raise ProfileContractError(f"keyPaths 指向的路径不存在: {value}")


def _unavailable_profile(binding: Any) -> dict[str, Any]:
    return {
        "repositoryId": binding.repository_id,
        "pathWithNamespace": binding.path_with_namespace or binding.repository_id,
        "role": "unknown",
        "responsibilitySummary": "无法读取该仓库，未进行画像分析",
        "techStack": [],
        "keyPaths": [],
        "confidence": 0.0,
        "evidence": [],
    }


def _string_list(value: Any, field: str, *, max_items: int) -> list[str]:
    if not isinstance(value, list):
        raise ProfileContractError(f"{field} 必须是数组")
    if len(value) > max_items:
        raise ProfileContractError(f"{field} 最多 {max_items} 项")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ProfileContractError(f"{field} 必须是非空字符串数组")
        text = item.strip()
        if "\n" in text or "\r" in text:
            raise ProfileContractError(f"{field} 不能包含换行")
        result.append(text)
    return result


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileContractError(f"{field} 必须是非空字符串")
    return value.strip()


def _one_line(value: str, field: str) -> str:
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise ProfileContractError(f"{field} 必须是单行文本")
    return text


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 字段: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"非法 JSON 数值: {value}")

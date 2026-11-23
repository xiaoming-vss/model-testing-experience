"""Validate the public repository profile artifact contract."""

import json
from typing import Any

PROFILE_ROLES = frozenset({"frontend", "backend", "fullstack", "infra", "test", "unknown"})
PROFILE_REPOSITORY_FIELDS = (
    "repositoryId",
    "pathWithNamespace",
    "role",
    "responsibilitySummary",
    "techStack",
    "keyPaths",
    "confidence",
    "evidence",
)


def parse_repository_profile(result_json: str | None) -> dict[str, Any] | None:
    """Parse the worker's exact profile JSON; malformed content stays readable as raw."""
    raw = str(result_json or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) != {"repositories", "overallSummary"}:
        return None
    repositories = data.get("repositories")
    overall_summary = data.get("overallSummary")
    if not isinstance(repositories, list) or not isinstance(overall_summary, str):
        return None
    if not overall_summary.strip():
        return None
    normalized: list[dict[str, Any]] = []
    for item in repositories:
        if not isinstance(item, dict):
            return None
        if set(item) != set(PROFILE_REPOSITORY_FIELDS):
            return None
        repository_id = item.get("repositoryId")
        path = item.get("pathWithNamespace")
        role = item.get("role")
        responsibility = item.get("responsibilitySummary")
        tech_stack = item.get("techStack")
        key_paths = item.get("keyPaths")
        confidence = item.get("confidence")
        evidence = item.get("evidence")
        if not isinstance(repository_id, str) or not repository_id.strip():
            return None
        if not isinstance(path, str) or not path.strip():
            return None
        if role not in PROFILE_ROLES:
            return None
        if not isinstance(responsibility, str) or not responsibility.strip():
            return None
        if (
            not _string_list(tech_stack)
            or not _string_list(key_paths)
            or not _string_list(evidence)
        ):
            return None
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            return None
        normalized.append(
            {
                "repositoryId": repository_id.strip(),
                "pathWithNamespace": path.strip(),
                "role": role,
                "responsibilitySummary": responsibility.strip(),
                "techStack": tech_stack,
                "keyPaths": key_paths,
                "confidence": float(confidence),
                "evidence": evidence,
            }
        )
    return {"repositories": normalized, "overallSummary": overall_summary.strip()}


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

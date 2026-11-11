"""Public UI input provenance, excluding clone URLs and authorization material."""

from copy import deepcopy
from typing import Any


def _public_repository(snapshot: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    return {
        "repositoryId": repository.get("repositoryId") or "",
        "pathWithNamespace": repository.get("pathWithNamespace") or "",
        "branch": repository.get("branch") or "",
        "commit": repository.get("commit") or "",
        "commitMode": repository.get("commitMode") or "",
        "profileVersionId": snapshot.get("sourceProfileVersionId") or "",
        "profileVersionNo": snapshot.get("sourceProfileVersionNo") or 0,
        "resolvedAt": repository.get("resolvedAt"),
    }


def ui_source_inputs(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose the frozen repository source identity and formal functional cases.

    Never returns clone URLs, connection IDs, or credentials.
    """
    if not snapshot:
        return None
    cases = snapshot.get("functionalCases")
    cases = deepcopy(cases) if isinstance(cases, list) else []
    repository = snapshot.get("sourceRepository")
    if isinstance(repository, dict) and repository:
        return {
            "sourceKind": "repository",
            "repository": _public_repository(snapshot, repository),
            "cases": cases,
        }
    return None


def public_ui_source_snapshot(source: dict[str, Any] | None) -> dict[str, Any]:
    """Strip worker-only fields from a UI run snapshot returned to browsers."""
    if not isinstance(source, dict):
        return {}
    repository = source.get("sourceRepository")
    safe: dict[str, Any] = {
        key: deepcopy(source[key])
        for key in (
            "sourceKind",
            "sourceType",
            "sourceContent",
            "sourceProfileVersionId",
            "sourceProfileVersionNo",
            "functionalCases",
            "uiWorkflowVersion",
            "uiSourceBatchId",
            "instruction",
        )
        if key in source
    }
    if isinstance(repository, dict) and repository:
        safe["sourceRepository"] = _public_repository(source, repository)
    return safe


__all__ = ["public_ui_source_snapshot", "ui_source_inputs"]

"""Explicit values crossing preparation and local import transactions."""

from dataclasses import dataclass
from typing import TypedDict

from testing_agent.schemas.bug_zentao_import import ZentaoImportSnapshot


class ImportStatus(TypedDict):
    status: str
    confirmed: bool
    resolution: str
    resolvedBuild: str


class ImportDescription(TypedDict):
    sanitized: str
    digest: str
    textOnly: str
    textOnlyDigest: str
    hasImages: bool
    hasContent: bool


class ResolvedBugImport(TypedDict):
    severity: str
    priority: str
    assignee_user_id: str
    found_sprint_id: str
    requirement_id: str
    duplicate_bug: int | None


class BugImportResult(TypedDict):
    remote_bug_id: int
    status: str
    bug_id: str
    bug_no: int
    title: str
    error_message: str
    pending: list[dict[str, str]]


@dataclass(frozen=True)
class PreparedBugImport:
    snapshot: ZentaoImportSnapshot
    status: ImportStatus
    description: ImportDescription
    resolved: ResolvedBugImport
    pending: list[dict[str, str]]


@dataclass(frozen=True)
class BugImportTarget:
    user_id: str
    project_id: str
    operation_id: str
    instance_url: str
    service_id: str
    remote_project_id: int


def import_result(
    remote_bug_id: int,
    status: str,
    *,
    bug_id: str = "",
    bug_no: int = 0,
    title: str = "",
    error_message: str = "",
    pending: list[dict[str, str]] | None = None,
) -> BugImportResult:
    return {
        "remote_bug_id": remote_bug_id,
        "status": status,
        "bug_id": bug_id,
        "bug_no": bug_no,
        "title": title,
        "error_message": error_message,
        "pending": pending or [],
    }

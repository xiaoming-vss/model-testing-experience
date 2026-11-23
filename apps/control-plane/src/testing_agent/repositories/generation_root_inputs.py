"""Lock current requirement document metadata for source verification."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_root_fingerprints import (
    IncompleteRootInput,
    fingerprint_root_input,
)
from testing_agent.domain.generation_source_closure import RootSnapshot
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.software_repository import SoftwareRepository
from testing_agent.models.sprint import Sprint
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.ai_generate_task import project_ui_source_cases
from testing_agent.repositories.api_generation_snapshot import project_api_generation_snapshot


async def lock_requirement_document_root(
    session: AsyncSession,
    *,
    requirement_id: str,
    referenced_attachment_ids: tuple[str, ...] | None,
) -> RootSnapshot:
    """Lock and fingerprint the current document and explicitly referenced images.

    The authorized caller must lock the project and sprint first. For rich text,
    ``referenced_attachment_ids`` must be obtained by parsing the actual frozen
    document, never from client claims; None means the references are unknown.
    This checks metadata, not the availability of the underlying S3 objects.
    """
    requirement = await session.scalar(
        select(Requirement)
        .where(Requirement.requirement_id == requirement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if requirement is None:
        raise IncompleteRootInput("requirement is unavailable")
    project_id = await session.scalar(
        select(Sprint.project_id).where(Sprint.sprint_id == requirement.sprint_id)
    )
    document_id = requirement.document_file_id
    if not project_id or not document_id:
        raise IncompleteRootInput("requirement document is unavailable")
    if requirement.document_type == "richtext" and referenced_attachment_ids is None:
        raise IncompleteRootInput("rich text attachment references are unknown")
    attachments = referenced_attachment_ids or ()
    if len(set(attachments)) != len(attachments) or document_id in attachments:
        raise IncompleteRootInput("requirement attachment identities are invalid")
    ids = (document_id, *attachments)
    files = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.file_id.in_(ids))
                .order_by(StoredFile.file_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    by_id = {item.file_id: item for item in files}
    if set(by_id) != set(ids):
        raise IncompleteRootInput("document or referenced attachment is missing")
    for file_id, file in by_id.items():
        expected_purpose = "requirement" if file_id == document_id else "attachment"
        if (
            file.project_id != project_id
            or file.resource_type != "requirement"
            or file.resource_id != requirement_id
            or file.purpose != expected_purpose
            or file.status != "attached"
            or not file.sha256
        ):
            raise IncompleteRootInput("document or attachment is unavailable or out of scope")
    document = by_id[document_id]
    if (
        document.sha256 != requirement.document_hash
        or document.filename != requirement.document_filename
    ):
        raise IncompleteRootInput("requirement document metadata is inconsistent")
    source = {
        "requirementId": requirement_id,
        "documentFileId": document_id,
        "documentHash": requirement.document_hash,
        "documentType": requirement.document_type,
        "documentFilename": requirement.document_filename,
        "attachmentHashes": [
            {"fileId": file_id, "sha256": by_id[file_id].sha256} for file_id in attachments
        ],
    }
    return fingerprint_root_input("requirement_document", source)


async def lock_revision_attachment_hashes(
    session: AsyncSession,
    *,
    project_id: str,
    file_ids: tuple[str, ...],
    expected_ownership: dict[str, tuple[str, str, str, str]] | None = None,
) -> dict[str, str]:
    """Lock retained revision images after their owning candidate sources."""
    if not file_ids:
        if expected_ownership:
            raise IncompleteRootInput("revision attachment ownership is inconsistent")
        return {}
    if any(not file_id for file_id in file_ids):
        raise IncompleteRootInput("revision attachment identity is unavailable")
    ids = tuple(sorted(set(file_ids)))
    expected_ownership = expected_ownership or {}
    if not set(expected_ownership).issubset(ids):
        raise IncompleteRootInput("revision attachment ownership is inconsistent")
    files = list(
        (
            await session.scalars(
                select(StoredFile)
                .where(StoredFile.file_id.in_(ids))
                .order_by(StoredFile.file_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if {item.file_id for item in files} != set(ids):
        raise IncompleteRootInput("revision attachment is missing")
    for file in files:
        if (
            file.project_id != project_id
            or file.purpose != "attachment"
            or file.resource_type != "ai_generate_run"
            or file.status != "attached"
            or not file.sha256
        ):
            raise IncompleteRootInput("revision attachment is unavailable or out of scope")
        expected = expected_ownership.get(file.file_id)
        if (
            expected
            and (
                file.resource_id,
                file.uploaded_by,
                file.filename,
                file.content_type,
            )
            != expected
        ):
            raise IncompleteRootInput("revision attachment ownership changed")
    return {file.file_id: file.sha256 for file in files}


async def lock_api_generation_source(
    session: AsyncSession, *, task: AiGenerateTask
) -> tuple[RootSnapshot, list[dict[str, Any]], list[dict[str, Any]]]:
    """Lock and project the API definitions actually selected by a task.

    The caller must already authorize and lock the project, requirement and
    task. Repositories are locked before interfaces, matching interface import.
    """
    ids = list(task.interface_ids_json or [])
    if (
        task.task_type != "api_case_generate"
        or not task.requirement_id
        or not ids
        or len(ids) != len(set(ids))
    ):
        raise IncompleteRootInput("API task or selected interfaces are unavailable")
    discovered = (
        await session.execute(
            select(ApiInterface.interface_id, ApiInterface.software_repository_id).where(
                ApiInterface.interface_id.in_(ids)
            )
        )
    ).all()
    associations = {row[0]: row[1] for row in discovered}
    if set(associations) != set(ids):
        raise IncompleteRootInput("selected API interface is unavailable")
    repository_ids = sorted(set(associations.values()))
    repositories = list(
        (
            await session.scalars(
                select(SoftwareRepository)
                .where(
                    SoftwareRepository.software_repository_id.in_(repository_ids),
                    SoftwareRepository.project_id == task.project_id,
                )
                .order_by(SoftwareRepository.software_repository_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if {item.software_repository_id for item in repositories} != set(repository_ids):
        raise IncompleteRootInput("API repository is unavailable or out of scope")
    interfaces = list(
        (
            await session.scalars(
                select(ApiInterface)
                .where(ApiInterface.interface_id.in_(ids))
                .order_by(ApiInterface.interface_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    current = {item.interface_id: item.software_repository_id for item in interfaces}
    if current != associations:
        raise IncompleteRootInput("API interface association changed during verification")
    repository_snapshot, interface_snapshot = project_api_generation_snapshot(
        ids, interfaces, sorted(repositories, key=lambda item: item.id)
    )
    root = fingerprint_root_input(
        "api_interfaces",
        {
            "taskId": task.task_id,
            "requirementId": task.requirement_id,
            "interfaces": interface_snapshot,
            "softwareRepositories": repository_snapshot,
        },
    )
    return root, repository_snapshot, interface_snapshot


async def lock_api_interface_root(session: AsyncSession, *, task: AiGenerateTask) -> RootSnapshot:
    """Lock and fingerprint selected API definitions without returning their contents."""
    root, _, _ = await lock_api_generation_source(session, task=task)
    return root


async def lock_ui_repository_cases_source(
    session: AsyncSession, *, task: AiGenerateTask, frozen_source: dict[str, Any]
) -> tuple[RootSnapshot, list[dict[str, Any]]]:
    """Lock and project selected formal cases against a frozen UI repository pin.

    The caller authorizes and locks the project, requirement and task, and
    supplies a server-stored source snapshot. This does not query GitLab HEAD;
    pin access and explicit source refresh remain separate operations.
    """
    selected = frozen_source.get("functionalCases")
    if (
        task.task_type != "ui_case_generate"
        or not task.requirement_id
        or (frozen_source.get("taskId") not in (None, "", task.task_id))
        or (frozen_source.get("requirementId") not in (None, "", task.requirement_id))
        or not isinstance(selected, list)
        or not selected
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("caseId"), str)
            or not item["caseId"]
            for item in selected
        )
    ):
        raise IncompleteRootInput("UI selected cases are unavailable")
    case_ids = [item["caseId"] for item in selected]
    if len(case_ids) != len(set(case_ids)):
        raise IncompleteRootInput("UI selected cases are duplicated")
    discovered = (
        await session.execute(
            select(FunctionTestCase.case_id, FunctionTestCase.suite_id).where(
                FunctionTestCase.case_id.in_(case_ids),
                FunctionTestCase.invalidated_at.is_(None),
            )
        )
    ).all()
    associations = {row[0]: row[1] for row in discovered}
    if set(associations) != set(case_ids):
        raise IncompleteRootInput("selected functional case is unavailable")
    suite_ids = sorted(set(associations.values()))
    suites = list(
        (
            await session.scalars(
                select(FunctionTestSuite)
                .where(
                    FunctionTestSuite.suite_id.in_(suite_ids),
                    FunctionTestSuite.requirement_id == task.requirement_id,
                )
                .order_by(FunctionTestSuite.suite_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    suite_by_id = {item.suite_id: item for item in suites}
    if set(suite_by_id) != set(suite_ids):
        raise IncompleteRootInput("functional suite is unavailable or out of scope")
    cases = list(
        (
            await session.scalars(
                select(FunctionTestCase)
                .where(
                    FunctionTestCase.case_id.in_(case_ids),
                    FunctionTestCase.invalidated_at.is_(None),
                )
                .order_by(FunctionTestCase.case_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if {item.case_id: item.suite_id for item in cases} != associations:
        raise IncompleteRootInput("functional case association changed during verification")
    ordered = sorted(
        cases, key=lambda item: (suite_by_id[item.suite_id].id, item.order_no, item.id)
    )
    snapshot = project_ui_source_cases((item, suite_by_id[item.suite_id].name) for item in ordered)
    root = fingerprint_root_input(
        "ui_repository_cases",
        {
            "taskId": task.task_id,
            "requirementId": task.requirement_id,
            "sourceRepository": frozen_source.get("sourceRepository"),
            "uiSourceBatchId": frozen_source.get("uiSourceBatchId"),
            "functionalCases": snapshot,
        },
    )
    return root, snapshot


async def lock_ui_repository_cases_root(
    session: AsyncSession, *, task: AiGenerateTask, frozen_source: dict[str, Any]
) -> RootSnapshot:
    """Recheck selected formal cases without returning their contents."""
    root, _ = await lock_ui_repository_cases_source(session, task=task, frozen_source=frozen_source)
    return root


async def read_requirement_file_metadata(
    session: AsyncSession, *, requirement_id: str, file_ids: tuple[str, ...]
) -> list[StoredFile]:
    """Read scoped metadata for object preparation; this does not acquire locks."""
    if not file_ids or len(file_ids) != len(set(file_ids)):
        raise IncompleteRootInput("requirement file identities are invalid")
    rows = list(
        (
            await session.scalars(
                select(StoredFile)
                .join(Sprint, Sprint.project_id == StoredFile.project_id)
                .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
                .where(
                    Requirement.requirement_id == requirement_id,
                    StoredFile.file_id.in_(file_ids),
                    StoredFile.resource_type == "requirement",
                    StoredFile.resource_id == requirement_id,
                    StoredFile.status == "attached",
                )
            )
        ).all()
    )
    if {row.file_id for row in rows} != set(file_ids):
        raise IncompleteRootInput("requirement file is unavailable or out of scope")
    return rows


async def read_requirement_document_identity(
    session: AsyncSession, *, requirement_id: str
) -> tuple[str, str, str]:
    """Read current document identity without locking; callers must recheck it."""
    row = (
        await session.execute(
            select(
                Requirement.document_file_id, Requirement.document_type, Requirement.document_hash
            ).where(Requirement.requirement_id == requirement_id)
        )
    ).one_or_none()
    if row is None or not all(row):
        raise IncompleteRootInput("requirement document is unavailable")
    return row[0], row[1], row[2]

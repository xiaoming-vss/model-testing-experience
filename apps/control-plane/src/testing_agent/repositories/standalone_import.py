"""Bounded reads and locked formal targets for independent import provenance."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite

_TARGETS: dict[str, tuple[Any, Any, Any, Any]] = {
    "function_suite": (
        FunctionTestSuite,
        FunctionTestSuite.suite_id,
        FunctionTestCase,
        FunctionTestCase.suite_id,
    ),
    "api_collection": (ApiCollection, ApiCollection.collection_id, ApiCase, ApiCase.collection_id),
    "ui_suite": (UiTestSuite, UiTestSuite.suite_id, UiTestCase, UiTestCase.suite_id),
}


async def import_records(session: AsyncSession, attempt_id: str) -> list[AiGenerateVersionImport]:
    rows = await session.scalars(
        select(AiGenerateVersionImport)
        .where(AiGenerateVersionImport.attempt_id == attempt_id)
        .order_by(AiGenerateVersionImport.imported_at, AiGenerateVersionImport.id)
    )
    return list(rows)


async def lock_target_and_count(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: str,
    project_id: str,
    changed_case_ids: tuple[str, ...],
) -> tuple[Any, int]:
    """Lock the formal target and verify every changed case and project ownership."""
    if (
        target_type not in _TARGETS
        or not target_id
        or len(set(changed_case_ids)) != len(changed_case_ids)
    ):
        raise ErrBadRequest()
    model, identity, case_model, case_parent = _TARGETS[target_type]
    target = await session.scalar(
        select(model)
        .join(Requirement, Requirement.requirement_id == model.requirement_id)
        .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
        .where(identity == target_id, Sprint.project_id == project_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise ErrNotFound()
    total = await session.scalar(
        select(func.count())
        .select_from(case_model)
        .where(case_parent == target_id)
        .with_for_update()
    )
    if changed_case_ids:
        count = await session.scalar(
            select(func.count())
            .select_from(case_model)
            .where(case_parent == target_id, case_model.case_id.in_(changed_case_ids))
            .with_for_update()
        )
        if count != len(changed_case_ids):
            raise ErrBadRequest()
    return target, int(total or 0)


async def requirement_project(session: AsyncSession, requirement_id: str) -> str | None:
    """Resolve a formal requirement's project within the caller's transaction."""
    return await session.scalar(
        select(Sprint.project_id)
        .join(Requirement, Requirement.sprint_id == Sprint.sprint_id)
        .where(Requirement.requirement_id == requirement_id)
    )

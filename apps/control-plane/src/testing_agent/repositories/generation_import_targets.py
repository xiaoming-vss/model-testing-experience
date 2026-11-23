"""Lock and fingerprint formal import targets without returning their contents."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.generation_source_closure import SourceClosureError
from testing_agent.domain.request_identity import request_signature
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.requirement import Requirement
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.schemas.requirement_design import DesignKind


@dataclass(frozen=True)
class ImportTargetState:
    requirement_id: str
    kind: DesignKind
    target_id: str
    fingerprint: str


def _row(row: Any) -> dict[str, Any]:
    """Include all persisted columns so new conflict-relevant fields fail closed."""
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.key)
        result[column.key] = value.isoformat() if isinstance(value, (datetime, date)) else value
    return result


async def lock_import_target_state(
    session: AsyncSession, *, requirement_id: str, kind: DesignKind, target_id: str
) -> ImportTargetState:
    """Lock every affected target and return its opaque deterministic fingerprint.

    The authorized caller must lock the project and sprint before this function.
    Functional imports can create or change several module suites, so their
    target is the entire requirement and ``target_id`` must be empty. API and UI
    imports use a single explicit target. Locks remain owned by the transaction.
    """
    requirement = await session.scalar(
        select(Requirement)
        .where(Requirement.requirement_id == requirement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if requirement is None:
        raise SourceClosureError("source_unknown")
    tables: dict[str, list[dict[str, Any]]] = {}
    if kind == "function":
        if target_id:
            raise SourceClosureError("source_conflict")
        suites = (
            await session.scalars(
                select(FunctionTestSuite)
                .where(FunctionTestSuite.requirement_id == requirement_id)
                .order_by(FunctionTestSuite.suite_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        suite_ids = [item.suite_id for item in suites]
        function_cases = (
            await session.scalars(
                select(FunctionTestCase)
                .where(FunctionTestCase.suite_id.in_(suite_ids))
                .order_by(FunctionTestCase.suite_id, FunctionTestCase.case_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        tables = {
            "suites": [_row(item) for item in suites],
            "cases": [_row(item) for item in function_cases],
        }
    elif kind == "api":
        target = await session.scalar(
            select(ApiCollection)
            .where(
                ApiCollection.requirement_id == requirement_id,
                ApiCollection.collection_id == target_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if target is None:
            raise SourceClosureError("source_unknown")
        api_cases = (
            await session.scalars(
                select(ApiCase)
                .where(ApiCase.collection_id == target_id)
                .order_by(ApiCase.case_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        case_ids = [item.case_id for item in api_cases]
        extracts = (
            await session.scalars(
                select(ApiExtractRule)
                .where(ApiExtractRule.case_id.in_(case_ids))
                .order_by(ApiExtractRule.case_id, ApiExtractRule.extract_rule_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        assertions = (
            await session.scalars(
                select(ApiAssertRule)
                .where(ApiAssertRule.case_id.in_(case_ids))
                .order_by(ApiAssertRule.case_id, ApiAssertRule.assert_rule_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        tables = {
            "target": [_row(target)],
            "cases": [_row(item) for item in api_cases],
            "extractRules": [_row(item) for item in extracts],
            "assertRules": [_row(item) for item in assertions],
        }
    elif kind == "ui":
        target = await session.scalar(
            select(UiTestSuite)
            .where(UiTestSuite.requirement_id == requirement_id, UiTestSuite.suite_id == target_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if target is None:
            raise SourceClosureError("source_unknown")
        ui_cases = (
            await session.scalars(
                select(UiTestCase)
                .where(UiTestCase.suite_id == target_id)
                .order_by(UiTestCase.case_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        tables = {"target": [_row(target)], "cases": [_row(item) for item in ui_cases]}
    else:
        raise SourceClosureError("source_unknown")
    fingerprint = request_signature(
        "generation-import-target-v1",
        {"requirementId": requirement_id, "kind": kind, "targetId": target_id, "tables": tables},
    )
    return ImportTargetState(requirement_id, kind, target_id, fingerprint)

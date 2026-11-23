"""Idempotent, self-contained receipts for current-content formal imports."""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_import_evidence import import_source_evidence
from testing_agent.domain.generation_import_source import CurrentImportSource
from testing_agent.models.ai_generate_import import AiGenerateImport, AiGenerateImportRequest
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite


async def read_completed_import_request(
    session: AsyncSession, *, request_id: str, fingerprint: str, requirement_id: str, actor_id: str
) -> dict[str, Any] | None:
    """Read a committed replay without requiring live generation sources."""
    row = await session.scalar(
        select(AiGenerateImportRequest)
        .where(AiGenerateImportRequest.request_id == request_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        return None
    if (
        row.request_fingerprint != fingerprint
        or row.requirement_id != requirement_id
        or row.actor_id != actor_id
        or row.completed_at is None
        or not isinstance(row.result_json, dict)
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他导入或回执不完整")
    return deepcopy(row.result_json)


async def reserve_import_request(
    session: AsyncSession, *, request_id: str, fingerprint: str, requirement_id: str, actor_id: str
) -> tuple[AiGenerateImportRequest, bool]:
    """Reserve or replay a completed request; caller owns outer transaction."""
    query = (
        select(AiGenerateImportRequest)
        .where(AiGenerateImportRequest.request_id == request_id)
        .execution_options(populate_existing=True)
    )
    row = await session.scalar(query)
    if row is None:
        reserved = AiGenerateImportRequest(
            request_id=request_id,
            request_fingerprint=fingerprint,
            requirement_id=requirement_id,
            actor_id=actor_id,
        )
        try:
            async with session.begin_nested():
                session.add(reserved)
                await session.flush()
            return reserved, False
        except IntegrityError:
            pass
        except OperationalError as exc:
            if (getattr(exc.orig, "args", ()) or (None,))[0] in {1205, 1213, 3572}:
                raise dynamic_error(ErrBadRequest, "导入请求正在处理中，请稍后重试") from exc
            raise
    row = await session.scalar(query.with_for_update())
    if row is None:
        raise dynamic_error(ErrBadRequest, "导入请求正在处理中，请稍后重试")
    if (
        row.request_fingerprint != fingerprint
        or row.requirement_id != requirement_id
        or row.actor_id != actor_id
        or row.completed_at is None
        or not isinstance(row.result_json, dict)
    ):
        raise dynamic_error(ErrBadRequest, "请求标识已用于其他导入或回执不完整")
    return row, True


async def record_current_import(
    session: AsyncSession,
    *,
    request: AiGenerateImportRequest,
    source: CurrentImportSource,
    target_id: str,
    actor_id: str,
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record imported targets and point each target to its durable receipt.

    The caller must hold source/target locks, apply assets in this transaction,
    and ensure no external commit occurs before these receipts are persisted.
    Change IDs are rechecked against their actual target, not trusted blindly.
    """
    if (
        request.completed_at is not None
        or request.result_json is not None
        or request.actor_id != actor_id
        or request.requirement_id != source.requirement_id
        or not changes
    ):
        raise ErrBadRequest()
    expected_type = {"function": "function_suite", "api": "api_collection", "ui": "ui_suite"}.get(
        source.kind
    )
    if expected_type is None:
        raise ErrBadRequest()
    evidence = import_source_evidence(source.source_snapshot)
    evidence["upstreamOutputs"] = deepcopy(list(source.upstream_outputs))
    now = datetime.now(UTC)
    records = []
    changed_ids: set[str] = set()
    seen_targets: set[str] = set()
    for change in changes:
        identifier = change.get("targetId")
        ids = change.get("changedCaseIds")
        if (
            change.get("targetType") != expected_type
            or not isinstance(identifier, str)
            or not identifier
            or identifier in seen_targets
            or (source.kind != "function" and identifier != target_id)
            or not isinstance(ids, list)
            or not ids
            or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ErrBadRequest()
        seen_targets.add(identifier)
        if source.kind == "function":
            target = await session.scalar(
                select(FunctionTestSuite)
                .where(
                    FunctionTestSuite.suite_id == identifier,
                    FunctionTestSuite.requirement_id == source.requirement_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            case_model: Any = FunctionTestCase
            parent = FunctionTestCase.suite_id
        elif source.kind == "api":
            target = await session.scalar(
                select(ApiCollection)
                .where(
                    ApiCollection.collection_id == identifier,
                    ApiCollection.requirement_id == source.requirement_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            case_model = ApiCase
            parent = ApiCase.collection_id
        else:
            target = await session.scalar(
                select(UiTestSuite)
                .where(
                    UiTestSuite.suite_id == identifier,
                    UiTestSuite.requirement_id == source.requirement_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            case_model = UiTestCase
            parent = UiTestCase.suite_id
        if target is None:
            raise ErrBadRequest()
        actual = set(
            (
                await session.scalars(
                    select(case_model.case_id)
                    .where(parent == identifier, case_model.case_id.in_(ids))
                    .with_for_update()
                )
            ).all()
        )
        if actual != set(ids):
            raise ErrBadRequest()
        count = await session.scalar(
            select(func.count())
            .select_from(case_model)
            .where(parent == identifier)
            .with_for_update()
        )
        if count is None or count < len(ids):
            raise ErrBadRequest()
        record = AiGenerateImport(
            import_id=f"gi-{uuid4().hex}",
            request_id=request.request_id,
            source_kind="current",
            requirement_id=source.requirement_id,
            task_id=source.task_id,
            kind=source.kind,
            stage=source.stage,
            source_attempt_id=source.source_attempt_id,
            source_candidate_id=source.candidate_id,
            source_snapshot_id=source.snapshot_id,
            source_content_token=source.content_token,
            content=source.content,
            format=source.format,
            content_hash=source.content_hash,
            basis_hash=source.basis_hash,
            lineage_hash=source.full_lineage_hash,
            source_manifest_json=deepcopy(source.source_manifest),
            source_snapshot_json=deepcopy(evidence),
            reviewer_user_id=source.confirmed_by,
            reviewed_at=source.confirmed_at,
            review_comment=source.review_comment,
            target_type=expected_type,
            target_id=identifier,
            changed_case_ids_json=sorted(ids),
            target_case_count=count,
            mixed_source=count > len(ids),
            imported_by=actor_id,
            imported_at=now,
        )
        session.add(record)
        target.effective_import_id = record.import_id
        records.append(
            {
                "importId": record.import_id,
                "targetType": expected_type,
                "targetId": identifier,
                "changedCaseIds": sorted(ids),
                "targetCaseCount": count,
            }
        )
        changed_ids.update(cast(list[str], ids))
    await session.flush()
    result = {"imported": True, "importRecords": records, "changedCaseIds": sorted(changed_ids)}
    request.result_json = deepcopy(result)
    request.completed_at = now
    await session.flush()
    return result

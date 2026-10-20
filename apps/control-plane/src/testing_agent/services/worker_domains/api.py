from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import ErrBadRequest, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.worker_context import ApiWorkerContext
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.schemas.workers import (
    WorkerTaskEventRequest,
)
from testing_agent.services.api_request_render import (
    api_case_request_template,
    render_api_case_request,
)
from testing_agent.services.execution_secrets import private_payload, protect_run, redact
from testing_agent.services.worker_domains.events import (
    ensure_final_status,
    final_run_status,
    json_text,
    parse_event_time,
)


def extracted_environment_values(
    extract_results: list[dict[str, Any]] | None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for result in extract_results or []:
        if not result.get("success"):
            continue
        var_key = str(result.get("varKey") or "").strip()
        if not var_key:
            continue
        values[var_key] = str(result.get("value") or "")
    return values


async def save_extracted_environment_vars(
    session: AsyncSession,
    environment_id: str,
    extract_results: list[dict[str, Any]] | None,
    *,
    actor: str,
) -> list[str]:
    secrets: list[str] = []
    if not environment_id:
        return secrets
    for var_key, value in extracted_environment_values(extract_results).items():
        env_var = await session.scalar(
            select(ApiEnvironmentVar).where(
                ApiEnvironmentVar.environment_id == environment_id,
                ApiEnvironmentVar.var_key == var_key,
            )
        )
        if env_var:
            if env_var.is_secret:
                if env_var.secret_user_id != actor:
                    raise ErrForbidden()
                secrets.append(value)
            env_var.value = value
        else:
            session.add(
                ApiEnvironmentVar(
                    env_var_id=new_id(),
                    environment_id=environment_id,
                    var_key=var_key,
                    value=value,
                    is_secret=True,
                    secret_user_id=actor,
                    description="",
                )
            )

            secrets.append(value)
    return secrets


async def api_case_worker_snapshot(
    session: AsyncSession,
    task: WorkerTask,
    run: ApiCaseRun | Any,
    context: ApiWorkerContext,
) -> dict[str, Any]:
    private = private_payload(run) if run else {}
    case_id = run.case_id if run else context.case_id
    collection_id = run.collection_id if run else context.collection_id
    environment_id = run.environment_id if run else ""
    request_snapshot = (
        (private.get("request_snapshot_json") or run.request_snapshot_json) if run else {}
    )
    runtime_vars = (private.get("runtime_vars_json") or run.runtime_vars_json) if run else {}

    if not request_snapshot and environment_id:
        api_case = await session.scalar(select(ApiCase).where(ApiCase.case_id == case_id))
        environment = await session.scalar(
            select(ApiEnvironment).where(ApiEnvironment.environment_id == environment_id)
        )
        if api_case and environment:
            env_vars = (
                await session.scalars(
                    select(ApiEnvironmentVar)
                    .where(ApiEnvironmentVar.environment_id == environment_id)
                    .order_by(ApiEnvironmentVar.created_at.asc())
                )
            ).all()
            rendered = render_api_case_request(api_case, environment, list(env_vars))
            request_snapshot = rendered.snapshot
            runtime_vars = rendered.runtime_vars

    api_case = await session.scalar(select(ApiCase).where(ApiCase.case_id == case_id))
    environment = (
        await session.scalar(
            select(ApiEnvironment).where(ApiEnvironment.environment_id == environment_id)
        )
        if environment_id
        else None
    )

    extract_rules = (
        await session.scalars(
            select(ApiExtractRule)
            .where(ApiExtractRule.case_id == case_id)
            .order_by(ApiExtractRule.order_no)
        )
    ).all()
    assert_rules = (
        await session.scalars(
            select(ApiAssertRule)
            .where(ApiAssertRule.case_id == case_id)
            .order_by(ApiAssertRule.order_no)
        )
    ).all()

    payload = {
        "taskId": task.task_id,
        "runId": run.run_id if run else task.run_id,
        "collectionId": collection_id,
        "caseId": case_id,
        "environmentId": environment_id,
        "request": request_snapshot or {},
        "runtimeVarsJson": json_text(runtime_vars or {}),
        "extractRules": [
            {
                "extractRuleId": rule.extract_rule_id,
                "name": rule.name,
                "enabled": rule.enabled,
                "orderNo": rule.order_no,
                "source": rule.source,
                "sourceExpr": rule.source_expr,
                "varKey": rule.var_key,
                "defaultValue": rule.default_value,
            }
            for rule in extract_rules
        ],
        "assertRules": [
            {
                "assertRuleId": rule.assert_rule_id,
                "name": rule.name,
                "enabled": rule.enabled,
                "orderNo": rule.order_no,
                "assertSource": rule.assert_source,
                "targetExpr": rule.target_expr,
                "comparator": rule.comparator,
                "expectedValue": rule.expected_value,
            }
            for rule in assert_rules
        ],
    }
    if (
        api_case
        and environment
        and hasattr(api_case, "url_template")
        and hasattr(environment, "base_url")
    ):
        payload["requestTemplate"] = api_case_request_template(api_case, environment)
    collection_run_id = getattr(run, "collection_run_id", "") or context.collection_run_id
    if collection_run_id:
        payload["collectionRunId"] = collection_run_id
    return payload


async def update_item_counts(session: AsyncSession, collection_run_id: str) -> None:
    items = (
        await session.scalars(
            select(ApiCollectionRunItem).where(
                ApiCollectionRunItem.collection_run_id == collection_run_id
            )
        )
    ).all()
    run = await session.scalar(
        select(ApiCollectionRun).where(ApiCollectionRun.collection_run_id == collection_run_id)
    )
    if run:
        run.success_count = sum(1 for item in items if item.status in {"success", "passed"})
        run.failed_count = sum(1 for item in items if item.status == RunStatus.FAILED.value)
        run.error_count = sum(1 for item in items if item.status == RunStatus.ERROR.value)
        run.skipped_count = sum(1 for item in items if item.status == RunStatus.SKIPPED.value)


async def build_snapshot(
    session: AsyncSession, task: WorkerTask, context: ApiWorkerContext
) -> dict[str, Any]:
    if context.collection_run_id:
        run = await session.scalar(
            select(ApiCollectionRun).where(
                ApiCollectionRun.collection_run_id == context.collection_run_id
            )
        )
        items = (
            await session.scalars(
                select(ApiCollectionRunItem)
                .where(ApiCollectionRunItem.collection_run_id == context.collection_run_id)
                .order_by(ApiCollectionRunItem.order_no)
            )
        ).all()
        environment = (
            await session.scalar(
                select(ApiEnvironment).where(ApiEnvironment.environment_id == run.environment_id)
            )
            if run
            else None
        )
        env_vars = (
            (
                await session.scalars(
                    select(ApiEnvironmentVar)
                    .where(ApiEnvironmentVar.environment_id == run.environment_id)
                    .order_by(ApiEnvironmentVar.created_at.asc())
                )
            ).all()
            if run
            else []
        )
        if run:
            protect_run(run, [row.value for row in env_vars if row.is_secret])
        collection_run: dict[str, Any] = {
            "taskId": task.task_id,
            "runId": task.run_id,
            "collectionRunId": context.collection_run_id,
            "collectionId": run.collection_id if run else context.collection_id,
            "environmentId": run.environment_id if run else "",
            "items": [],
        }
        for item in items:
            api_case = await session.scalar(select(ApiCase).where(ApiCase.case_id == item.case_id))
            request_snapshot: dict[str, Any] = {}
            runtime_vars: dict[str, Any] = {}
            if api_case and environment:
                rendered = render_api_case_request(api_case, environment, list(env_vars))
                request_snapshot = rendered.snapshot
                runtime_vars = rendered.runtime_vars
            case_run = SimpleNamespace(
                run_id="",
                collection_run_id=context.collection_run_id,
                collection_id=run.collection_id if run else context.collection_id,
                case_id=item.case_id,
                environment_id=run.environment_id if run else "",
                request_snapshot_json=request_snapshot,
                runtime_vars_json=runtime_vars,
            )
            collection_run["items"].append(
                {
                    "itemId": item.item_id,
                    "continueOnFailure": item.continue_on_failure,
                    "enabled": api_case.enabled if api_case else True,
                    "caseName": api_case.name if api_case else "",
                    "orderNo": item.order_no,
                    "caseRun": await api_case_worker_snapshot(session, task, case_run, context),
                }
            )
        return {"taskType": task.task_type, "collectionRun": collection_run}
    else:
        run = await session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == task.run_id))
        return {
            "taskType": task.task_type,
            "caseRun": await api_case_worker_snapshot(session, task, run, context),
        }


async def complete_run(
    session: AsyncSession, task: WorkerTask, body: WorkerTaskEventRequest
) -> None:
    status = final_run_status(body.status)
    if task.task_type == "api_collection_run":
        run = await session.scalar(
            select(ApiCollectionRun).where(ApiCollectionRun.collection_run_id == task.run_id)
        )
        if run:
            items = (
                await session.scalars(
                    select(ApiCollectionRunItem).where(
                        ApiCollectionRunItem.collection_run_id == task.run_id
                    )
                )
            ).all()
            success_count = sum(1 for item in items if item.status in {"success", "passed"})
            failed_count = sum(1 for item in items if item.status == RunStatus.FAILED.value)
            error_count = sum(1 for item in items if item.status == RunStatus.ERROR.value)
            skipped_count = sum(1 for item in items if item.status == RunStatus.SKIPPED.value)
            run.success_count = success_count
            run.failed_count = failed_count
            run.error_count = error_count
            run.skipped_count = skipped_count
            if status in {RunStatus.CANCELED.value, RunStatus.FAILED.value}:
                run.status = status
            elif (
                status == RunStatus.ERROR.value
                and success_count == 0
                and failed_count == 0
                and error_count == 0
            ):
                run.status = RunStatus.ERROR.value
            elif error_count > 0:
                run.status = RunStatus.ERROR.value
            elif failed_count > 0:
                run.status = RunStatus.FAILED.value
            else:
                run.status = RunStatus.SUCCESS.value
            run.error_message = body.error_message or ""
            if not run.error_message:
                parts = []
                if failed_count:
                    parts.append(f"{failed_count}个用例失败")
                if error_count:
                    parts.append(f"{error_count}个用例异常")
                if skipped_count:
                    parts.append(f"{skipped_count}个用例跳过")
                run.error_message = "，".join(parts)
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms
            protect_run(run, [])
    else:
        run = await session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == task.run_id))
        if run:
            run.status = status
            run.request_snapshot_json = (
                body.request or body.snapshot_json or run.request_snapshot_json
            )
            run.response_snapshot_json = body.response or run.response_snapshot_json
            run.runtime_vars_json = body.runtime_vars_json or run.runtime_vars_json
            run.extract_results_json = body.extract_results or run.extract_results_json
            secrets = await save_extracted_environment_vars(
                session, run.environment_id, body.extract_results, actor=run.trigger_user_id
            )
            run.assert_results_json = (
                body.assert_results or body.step_results or run.assert_results_json
            )
            run.error_message = body.error_message or ""
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms
            protect_run(run, secrets)


async def start_item(
    repository: WorkerTaskRepository, task: WorkerTask, item_id: str, body: WorkerTaskEventRequest
) -> None:
    if task.task_type != "api_collection_run":
        raise ErrBadRequest()
    item = await repository.get_api_item(item_id)
    if item is None:
        raise ErrNotFound()
    if getattr(item, "collection_run_id", task.run_id) != task.run_id:
        raise ErrBadRequest()
    item.status = RunStatus.RUNNING.value
    item.started_at = parse_event_time(body.started_at) or datetime.now(UTC)


async def complete_item(
    repository: WorkerTaskRepository,
    task: WorkerTask,
    item_id: str,
    body: WorkerTaskEventRequest,
    *,
    id_factory: Callable[[], str] = new_id,
) -> str:
    if task.task_type != "api_collection_run":
        raise ErrBadRequest()
    status = ensure_final_status(body.status, {"success", "failed", "error", "skipped"})
    item = await repository.get_api_item(item_id)
    if item is None:
        raise ErrNotFound()
    if getattr(item, "collection_run_id", task.run_id) != task.run_id:
        raise ErrBadRequest()
    collection_run = await repository.get_api_collection_run(item.collection_run_id)
    if collection_run is None:
        raise ErrNotFound()
    item.status = status
    started_at = parse_event_time(body.started_at)
    finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
    case_run = ApiCaseRun(
        run_id=id_factory(),
        collection_run_id=item.collection_run_id,
        case_id=body.case_id or item.case_id,
        collection_id=collection_run.collection_id,
        environment_id=collection_run.environment_id,
        trigger_user_id=collection_run.trigger_user_id,
        trigger_type="collection",
        status=item.status,
        request_snapshot_json=body.request or {},
        response_snapshot_json=body.response or {},
        runtime_vars_json=body.runtime_vars_json or {},
        extract_results_json=body.extract_results or [],
        assert_results_json=body.assert_results or body.step_results or [],
        error_message=body.error_message or "",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=body.duration_ms or 0,
    )
    repository.add(case_run)
    secrets = await save_extracted_environment_vars(
        repository.session,
        collection_run.environment_id,
        body.extract_results,
        actor=collection_run.trigger_user_id,
    )
    secrets.extend(private_payload(collection_run).get("secrets", []))
    protect_run(case_run, secrets)
    protect_run(collection_run, secrets)
    item.case_run_id = case_run.run_id
    item.started_at = started_at
    item.error_message = redact(body.error_message or "", secrets)
    item.finished_at = finished_at
    if body.duration_ms is not None:
        item.duration_ms = body.duration_ms
    await update_item_counts(repository.session, item.collection_run_id)
    return item.status


async def mark_claimed(
    repository: WorkerTaskRepository, task: WorkerTask, context: ApiWorkerContext
) -> None:
    run: ApiCaseRun | ApiCollectionRun | None
    if not isinstance(context, ApiWorkerContext):
        raise ErrBadRequest()
    if context.collection_run_id:
        run = await repository.get_api_collection_run(context.collection_run_id)
    else:
        run = await repository.get_api_run(task.run_id)
    if run is None:
        raise ErrNotFound()
    run.status = RunStatus.QUEUED.value


async def mark_started(
    repository: WorkerTaskRepository, task: WorkerTask, started_at: datetime | None
) -> None:
    run: ApiCaseRun | ApiCollectionRun | None
    if task.task_type == "api_collection_run":
        run = await repository.get_api_collection_run(task.run_id)
    else:
        run = await repository.get_api_run(task.run_id)
    if run:
        run.status = RunStatus.RUNNING.value
        if getattr(run, "started_at", None) is None:
            run.started_at = started_at or datetime.now(UTC)

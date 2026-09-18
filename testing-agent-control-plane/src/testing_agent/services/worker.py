from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection_run import ApiCollectionRun, ApiCollectionRunItem
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun, UiTestSuiteRunItem
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.api_request_render import (
    api_case_request_template,
    render_api_case_request,
)
from testing_agent.services.execution_secrets import private_payload, protect_run
from testing_agent.services.ui_execution_payload import (
    ui_case_payload as ui_case_model_payload,
)
from testing_agent.services.ui_execution_payload import (
    ui_suite_payload as ui_suite_model_payload,
)

LEASE_SECONDS = 30


def final_run_status(status: str | None) -> str:
    if status is None or status in {"", "completed", "passed", "success"}:
        return "success"
    if status in {"failed", "failure"}:
        return "failed"
    return status


def task_payload(task: WorkerTask) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "domain": task.domain,
        "runId": task.run_id,
        "suiteId": task.suite_id,
        "caseId": task.case_id,
        "collectionRunId": task.collection_run_id,
        "collectionId": task.collection_id,
        "generateTaskId": task.generate_task_id,
        "status": task.status,
    }


def llm_credentials_payload(
    task_id: str,
    connection: IntegrationConnection | Any | None,
    cipher: Any | None = None,
) -> dict[str, Any]:
    if connection is None:
        return {"taskId": task_id, "baseUrl": "", "modelId": "", "apiKey": ""}
    secret = connection.secret_json or {}
    extra = connection.extra_json or {}
    api_key = secret.get("apiKey") or secret.get("api_key") or connection.access_token
    if api_key and cipher is not None:
        try:
            api_key = cipher.decrypt(api_key)
        except ValueError:
            # 凭据损坏(密钥轮换或手工改动):不下发,任务侧会因缺 key 失败并提示重配。
            api_key = ""
    model_id = (
        secret.get("modelId")
        or secret.get("model")
        or secret.get("model_id")
        or extra.get("modelId")
        or extra.get("model")
        or extra.get("model_id")
        or ""
    )
    return {
        "taskId": task_id,
        "connectionId": connection.connection_id,
        "baseUrl": connection.base_url,
        "modelId": model_id,
        "apiKey": api_key,
        "organization": extra.get("organization") or secret.get("organization") or "",
    }


def project_skill_worker_payload(skill: ProjectSkillSpace) -> dict[str, Any]:
    return {
        "skillSpaceId": skill.skill_space_id,
        "projectId": skill.project_id,
        "version": skill.version,
        "hash": skill.hash,
        "downloadUrl": skill.download_url,
        "filename": skill.filename,
        "size": skill.size_bytes,
        "isDefault": skill.is_default,
    }


def json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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
                    raise ErrForbidden
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


def apply_ai_completion_to_run(
    run: AiGenerateTaskRun | Any, body: WorkerTaskEventRequest, *, functional: bool = False
):
    snapshot = body.snapshot_json or {}
    status = final_run_status(body.status)
    run.status = status
    current_stage = snapshot.get("currentStage") or snapshot.get("stage")
    if current_stage is not None:
        run.current_stage = str(current_stage)
    stage_status = snapshot.get("stageStatus")
    if stage_status is not None:
        run.stage_status = str(stage_status)
    elif status == RunStatus.SUCCESS.value:
        run.stage_status = StageStatus.COMPLETED.value
        run.current_stage = "completed"
    elif status in {"failed", "error", "canceled"}:
        run.stage_status = StageStatus.FAILED.value
    run.error_message = body.error_message or snapshot.get("errorMessage") or ""
    run.remediation = body.remediation or snapshot.get("remediation") or ""
    if not functional or status == RunStatus.SUCCESS.value:
        if body.config_json is not None:
            run.config_json = body.config_json
        elif snapshot.get("configJson") is not None:
            run.config_json = snapshot.get("configJson")
        output_yaml = getattr(body, "output_yaml", None)
        if body.result_yaml is not None:
            run.result_yaml = body.result_yaml
        elif output_yaml is not None:
            run.result_yaml = output_yaml
        elif snapshot.get("resultYaml") is not None:
            run.result_yaml = str(snapshot.get("resultYaml"))
        elif snapshot.get("outputYaml") is not None:
            run.result_yaml = str(snapshot.get("outputYaml"))
    if body.result_summary_json is not None:
        run.result_summary_json = body.result_summary_json
    elif snapshot.get("resultSummaryJson") is not None:
        run.result_summary_json = snapshot.get("resultSummaryJson")
    run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
    if body.duration_ms is not None:
        run.duration_ms = body.duration_ms


def parse_event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def find_task(session: AsyncSession, domain: str, task_id: str) -> WorkerTask:
    task = await session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == domain, WorkerTask.task_id == task_id)
        .with_for_update()
    )
    if task is None:
        raise ErrNotFound
    from testing_agent.services.worker_context import hydrate

    return await session.run_sync(lambda sync: hydrate(sync, task))


async def api_case_worker_snapshot(
    session: AsyncSession,
    task: WorkerTask,
    run: ApiCaseRun | Any,
) -> dict[str, Any]:
    private = private_payload(run) if run else {}
    case_id = run.case_id if run else task.case_id
    collection_id = run.collection_id if run else task.collection_id
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
    collection_run_id = getattr(run, "collection_run_id", "") or task.collection_run_id
    if collection_run_id:
        payload["collectionRunId"] = collection_run_id
    return payload


async def build_snapshot(session: AsyncSession, domain: str, task: WorkerTask) -> dict[str, Any]:
    if domain == "ai":
        run = await session.scalar(
            select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == task.run_id)
        )
        if run is None:
            return {
                "taskType": task.task_type,
                "checkpointEnabled": False,
                "currentStage": "",
                "configJson": "{}",
                "run": None,
            }
        snapshot = dict(run.snapshot_json or {})
        config = run.config_json or {}
        if isinstance(run, AiGenerateTaskRun):
            from testing_agent.services.ai_execution import worker_input

            snapshot, config = await session.run_sync(
                lambda sync_session: worker_input(sync_session, run, task)
            )
        if snapshot:
            snapshot["runId"] = run.run_id
            document_type = snapshot.get("documentType") or snapshot.get("sourceType")
            if snapshot.get("taskType") in {
                "requirement_analysis",
                "functional_case_generate",
            } and document_type in {"text", "word", "docx"}:
                document_url = f"/internal/ai-worker/tasks/{task.task_id}/requirement-document"
                snapshot["documentDownloadUrl"] = document_url
                if document_type in {"word", "docx"} and not snapshot.get("sourceContent"):
                    snapshot["sourceContent"] = document_url
        return {
            "taskType": task.task_type,
            "checkpointEnabled": run.checkpoint_enabled,
            "currentStage": run.current_stage,
            "configJson": json_text(config),
            "run": snapshot or None,
        }
    if domain == "api" and task.collection_run_id:
        run = await session.scalar(
            select(ApiCollectionRun).where(
                ApiCollectionRun.collection_run_id == task.collection_run_id
            )
        )
        items = (
            await session.scalars(
                select(ApiCollectionRunItem)
                .where(ApiCollectionRunItem.collection_run_id == task.collection_run_id)
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
        collection_run = {
            "taskId": task.task_id,
            "runId": task.run_id,
            "collectionRunId": task.collection_run_id,
            "collectionId": run.collection_id if run else task.collection_id,
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
                collection_run_id=task.collection_run_id,
                collection_id=run.collection_id if run else task.collection_id,
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
                    "caseRun": await api_case_worker_snapshot(session, task, case_run),
                }
            )
        return {"taskType": task.task_type, "collectionRun": collection_run}
    elif domain == "api":
        run = await session.scalar(select(ApiCaseRun).where(ApiCaseRun.run_id == task.run_id))
        return {
            "taskType": task.task_type,
            "caseRun": await api_case_worker_snapshot(session, task, run),
        }
    payload = task_payload(task)
    if domain == "ui" and task.task_type == "suite_run":
        run = await session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
        )
        suite_run = dict(run.snapshot_json or {}) if run else {}
        if run:
            items = (
                await session.scalars(
                    select(UiTestSuiteRunItem)
                    .where(UiTestSuiteRunItem.suite_run_id == task.run_id)
                    .order_by(UiTestSuiteRunItem.order_no)
                )
            ).all()
            suite_run["items"] = [
                dict(item.snapshot_json or {})
                or {
                    "itemId": item.item_id,
                    "caseId": item.case_id,
                    "orderNo": item.order_no,
                    "continueOnFailure": item.continue_on_failure,
                    "status": item.status,
                }
                for item in items
            ]
        payload["suiteRun"] = suite_run
    elif domain == "ui":
        run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
        payload["caseRun"] = dict(run.snapshot_json or {}) if run else {}
    return payload


def ui_suite_payload(suite: Any | None) -> dict[str, Any]:
    return ui_suite_model_payload(suite)


async def ui_case_payload(session: AsyncSession, case_id: str) -> dict[str, Any]:
    case = await session.scalar(select(UiTestCase).where(UiTestCase.case_id == case_id))
    return ui_case_model_payload(case)


async def update_task_claimed(task: WorkerTask, body: WorkerClaimRequest):
    now = datetime.now(UTC)
    task.worker_id = body.worker_id
    task.status = RunStatus.CLAIMED.value
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)


async def apply_event_to_task(task: WorkerTask, body: WorkerTaskEventRequest, status: str | None):
    now = datetime.now(UTC)
    task.worker_id = body.worker_id
    if status:
        task.status = status
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    if body.started_at:
        task.started_at = parse_event_time(body.started_at)
    if body.finished_at or status in {"success", "failed", "error", "completed"}:
        task.finished_at = parse_event_time(body.finished_at) or now
    if body.error_message is not None:
        task.error_message = body.error_message


async def complete_domain_run(
    session: AsyncSession, domain: str, task: WorkerTask, body: WorkerTaskEventRequest
):
    status = final_run_status(body.status)
    if domain == "api" and task.collection_run_id:
        run = await session.scalar(
            select(ApiCollectionRun).where(
                ApiCollectionRun.collection_run_id == task.collection_run_id
            )
        )
        if run:
            items = (
                await session.scalars(
                    select(ApiCollectionRunItem).where(
                        ApiCollectionRunItem.collection_run_id == task.collection_run_id
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
    elif domain == "api":
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
    elif domain == "ui" and task.task_type == "suite_run":
        run = await session.scalar(
            select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == task.run_id)
        )
        if run:
            run.status = status
            run.error_message = body.error_message or ""
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms
    elif domain == "ui":
        run = await session.scalar(select(UiTestCaseRun).where(UiTestCaseRun.run_id == task.run_id))
        if run:
            run.status = status
            run.step_results_json = body.step_results or run.step_results_json
            run.error_message = body.error_message or ""
            run.finished_at = parse_event_time(body.finished_at) or datetime.now(UTC)
            if body.duration_ms is not None:
                run.duration_ms = body.duration_ms
    elif domain == "ai":
        run = await session.scalar(
            select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == task.run_id)
        )
        if run:
            apply_ai_completion_to_run(
                run, body, functional=task.task_type == "functional_case_generate"
            )


async def update_item_counts(session: AsyncSession, collection_run_id: str):
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


async def update_ui_item_counts(session: AsyncSession, suite_run_id: str):
    items = (
        await session.scalars(
            select(UiTestSuiteRunItem).where(UiTestSuiteRunItem.suite_run_id == suite_run_id)
        )
    ).all()
    run = await session.scalar(
        select(UiTestSuiteRun).where(UiTestSuiteRun.suite_run_id == suite_run_id)
    )
    if run:
        run.success_count = sum(1 for item in items if item.status in {"success", "passed"})
        run.failed_count = sum(1 for item in items if item.status == RunStatus.FAILED.value)
        run.error_count = sum(1 for item in items if item.status == RunStatus.ERROR.value)
        run.skipped_count = sum(1 for item in items if item.status == RunStatus.SKIPPED.value)

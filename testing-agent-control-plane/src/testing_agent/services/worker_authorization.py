"""Recheck an execution's recorded actor before delivering inputs or credentials."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from testing_agent.core.enums import RunStatus, StageStatus
from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generate_execution import AiGenerateRunStage, AiGenerateStageAttempt
from testing_agent.models.ai_generate_task import AiGenerateTaskRun
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.user import User
from testing_agent.services.environment_access import authorized_environment_vars
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import require_project_id


@dataclass
class ExecutionAuthority:
    actor: str
    project_id: str
    run: Any
    connection_ids: list[tuple[str, str]]


async def execution_authority(session, task) -> ExecutionAuthority:
    if task.domain == "ai":
        run = await session.scalar(
            select(AiGenerateTaskRun).where(AiGenerateTaskRun.run_id == task.run_id)
        )
        attempt = await session.scalar(
            select(AiGenerateStageAttempt)
            .join(AiGenerateRunStage, AiGenerateRunStage.id == AiGenerateStageAttempt.stage_id)
            .where(
                AiGenerateRunStage.run_id == task.run_id,
                AiGenerateStageAttempt.worker_task_id == task.task_id,
            )
            .order_by(
                AiGenerateRunStage.stage_order.desc(), AiGenerateStageAttempt.attempt_no.desc()
            )
        )
        if run is None or attempt is None or not attempt.requested_by:
            raise ErrForbidden
        from testing_agent.services.ai_execution import project

        run = await session.run_sync(lambda sync: project(sync, run))
        snapshot = attempt.input_snapshot_json or {}
        connections = [("llm", str(snapshot.get("llmConnectionId") or ""))]
        for binding in (snapshot.get("source") or {}).get("bindings", []):
            connections.append(("gitlab", str(binding.get("connectionId") or "")))
        return ExecutionAuthority(attempt.requested_by, run.project_id, run, connections)
    model: Any
    container: Any
    if task.domain == "api":
        model, key = (
            (ApiCollectionRun, "collection_run_id")
            if task.task_type == "api_collection_run"
            else (ApiCaseRun, "run_id")
        )
        container, field = ApiCollection, "collection_id"
    else:
        model, key = (
            (UiTestSuiteRun, "suite_run_id")
            if task.task_type == "suite_run"
            else (UiTestCaseRun, "run_id")
        )
        container, field = UiTestSuite, "suite_id"
    run = await session.scalar(select(model).where(getattr(model, key) == task.run_id))
    if run is None:
        raise ErrForbidden
    project_id = await session.scalar(
        select(Sprint.project_id)
        .select_from(container)
        .join(Requirement, Requirement.requirement_id == container.requirement_id)
        .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
        .where(
            getattr(container, field) == getattr(run, field),
        )
    )
    if not project_id:
        raise ErrForbidden
    return ExecutionAuthority(run.trigger_user_id, project_id, run, [])


async def fail_authorization(session, task, authority=None):
    from testing_agent.services.ai_execution import persist, project

    now = datetime.now(UTC)
    task.status = RunStatus.FAILED.value
    task.error_message = "操作人的项目访问或个人授权已失效，请配置本人授权后重新执行"
    task.finished_at = now
    task.lease_expires_at = now
    if authority:
        run = authority.run
        if task.domain == "ai":
            run = await session.run_sync(lambda sync: project(sync, run))
            run.stage_status = StageStatus.FAILED.value
            run._worker_event = task.task_id
        run.status = RunStatus.FAILED.value
        run.error_message = task.error_message
        run.finished_at = now
    await session.run_sync(persist)


async def authorize_execution(session, task, *, pending=False) -> ExecutionAuthority:
    if task.status not in (
        {RunStatus.PENDING.value, RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
        if pending
        else {RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
    ):
        raise ErrForbidden
    authority = None
    try:
        authority = await execution_authority(session, task)
        if not await session.scalar(select(User.user_id).where(User.user_id == authority.actor)):
            raise ErrForbidden
        await require_project_id(session, authority.actor, authority.project_id)
        for provider, connection_id in authority.connection_ids:
            connection = await require_personal_connection(
                session, authority.actor, provider, connection_id, authority.project_id
            )
            if provider == "gitlab":
                from testing_agent.services.service_instance import normalize_instance_url

                bindings = (authority.run.snapshot_json or {}).get("bindings", [])
                if any(
                    binding.get("connectionId") == connection_id
                    and binding.get("instanceUrl") != normalize_instance_url(connection.base_url)
                    for binding in bindings
                ):
                    raise ErrForbidden
        if task.domain == "api":
            await authorized_environment_vars(
                session, authority.actor, authority.run.environment_id
            )
    except AppError:
        await fail_authorization(session, task, authority)
        await session.commit()
        raise ErrForbidden from None
    return authority


async def revoke_executions(
    session, *, actor: str = "", project_id: str = "", connection_id: str = ""
):
    """Record revocation in the same transaction; rejoining cannot revive queued work."""
    from testing_agent.models.worker_task import WorkerTask

    tasks = list(
        (
            await session.scalars(
                select(WorkerTask)
                .where(
                    WorkerTask.status.in_(
                        (RunStatus.PENDING.value, RunStatus.CLAIMED.value, RunStatus.RUNNING.value)
                    )
                )
                .with_for_update()
            )
        ).all()
    )
    for task in tasks:
        try:
            authority = await execution_authority(session, task)
        except AppError:
            continue
        if actor and authority.actor != actor:
            continue
        if project_id and authority.project_id != project_id:
            continue
        if connection_id and not any(cid == connection_id for _, cid in authority.connection_ids):
            continue
        await fail_authorization(session, task, authority)

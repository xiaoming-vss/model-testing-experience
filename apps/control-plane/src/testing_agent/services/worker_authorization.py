"""Recheck an execution's recorded actor before delivering inputs or credentials."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, exists, or_, select

from testing_agent.core.enums import RunStatus
from testing_agent.core.errors import AppError, ErrForbidden
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.models.api_case_run import ApiCaseRun
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_collection_run import ApiCollectionRun
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.ui_test_case_run import UiTestCaseRun
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.ui_test_suite_run import UiTestSuiteRun
from testing_agent.models.user import User
from testing_agent.models.worker_task import WorkerTask
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
    if task.domain not in {"api", "ui"}:
        raise ErrForbidden()
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
    row = (
        await session.execute(
            select(model, Sprint.project_id)
            .select_from(model)
            .join(container, getattr(container, field) == getattr(model, field))
            .join(Requirement, Requirement.requirement_id == container.requirement_id)
            .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
            .where(getattr(model, key) == task.run_id)
        )
    ).one_or_none()
    if row is None or not row[1]:
        raise ErrForbidden()
    run, project_id = row
    return ExecutionAuthority(run.trigger_user_id, project_id, run, [])


async def fail_authorization(session, task, authority=None):
    if task.domain not in {"api", "ui"}:
        raise ErrForbidden()
    now = datetime.now(UTC)
    message = "操作人的项目访问或个人授权已失效，请配置本人授权后重新执行"
    if task.domain in {"api", "ui"}:
        from testing_agent.services.test_run_stop import finish_stopped_items

        await finish_stopped_items(session, task, interrupted=True, reason=message)
    task.status = RunStatus.FAILED.value
    task.error_message = message
    task.finished_at = now
    task.lease_expires_at = now
    if authority:
        run = authority.run
        run.status = RunStatus.FAILED.value
        run.error_message = task.error_message
        run.finished_at = now
        if isinstance(run, UiTestCaseRun):
            from testing_agent.services.worker_domains.ui import close_running_steps

            run.step_results_json = close_running_steps(run.step_results_json, "error", message)


async def authorize_execution(session, task, *, pending=False) -> ExecutionAuthority:
    if task.domain not in {"api", "ui"}:
        raise ErrForbidden()
    if task.status not in (
        {RunStatus.PENDING.value, RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
        if pending
        else {RunStatus.CLAIMED.value, RunStatus.RUNNING.value}
        | ({RunStatus.STOPPING.value} if task.domain in {"api", "ui"} else set())
    ):
        raise ErrForbidden()
    authority = None
    try:
        authority = await execution_authority(session, task)
        if not await session.scalar(select(User.user_id).where(User.user_id == authority.actor)):
            raise ErrForbidden()
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
                    raise ErrForbidden()
        if task.domain == "api":
            await authorized_environment_vars(
                session, authority.actor, authority.run.environment_id
            )
    except AppError:
        should_notify = task.domain in {"api", "ui"} and task.status in {
            "pending",
            "claimed",
            "running",
            "stopping",
        }
        await fail_authorization(session, task, authority)
        await session.commit()
        if should_notify:
            from testing_agent.services.test_run_notifications import (
                notify_run_changed,
                notify_task_control,
            )

            await notify_run_changed(task.domain, task.run_id)
            await notify_task_control(task.task_id)
        raise ErrForbidden() from None
    return authority


def _actor_execution_filter(actor: str):
    """Restrict the revocation lock set to tasks started by this actor.

    Locking every active queue row blocked unrelated runs while a member was
    removed. Filtering by the recorded trigger user keeps the lock window
    proportional to the revoked actor's own work.
    """
    return or_(
        and_(
            WorkerTask.domain == "ai",
            exists().where(
                AiGenerationAttempt.id == WorkerTask.run_id,
                AiGenerationAttempt.requested_by == actor,
            ),
        ),
        and_(
            WorkerTask.domain == "api",
            or_(
                exists().where(
                    ApiCaseRun.run_id == WorkerTask.run_id,
                    ApiCaseRun.trigger_user_id == actor,
                ),
                exists().where(
                    ApiCollectionRun.collection_run_id == WorkerTask.run_id,
                    ApiCollectionRun.trigger_user_id == actor,
                ),
            ),
        ),
        and_(
            WorkerTask.domain == "ui",
            or_(
                exists().where(
                    UiTestCaseRun.run_id == WorkerTask.run_id,
                    UiTestCaseRun.trigger_user_id == actor,
                ),
                exists().where(
                    UiTestSuiteRun.suite_run_id == WorkerTask.run_id,
                    UiTestSuiteRun.trigger_user_id == actor,
                ),
            ),
        ),
    )


async def revoke_executions(
    session, *, actor: str = "", project_id: str = "", connection_id: str = ""
) -> list[tuple[str, str, str]]:
    """Record revocation in the same transaction; rejoining cannot revive queued work."""
    from testing_agent.services.integration_lifecycle import revoke_integrations

    if actor or project_id or connection_id:
        await revoke_integrations(
            session, actor=actor, project_id=project_id, connection_id=connection_id
        )

    candidate = select(WorkerTask).where(
        WorkerTask.status.in_(
            (RunStatus.PENDING.value, RunStatus.CLAIMED.value, RunStatus.RUNNING.value)
        )
    )
    if actor:
        candidate = candidate.where(_actor_execution_filter(actor))
    tasks = list((await session.scalars(candidate.with_for_update())).all())
    notifications = []
    for task in tasks:
        if task.domain == "ai":
            from testing_agent.services.stage_storage.authorization import (
                direct_revocation_identity,
            )
            from testing_agent.services.stage_storage.worker_service import DirectStageWorkerService

            direct = DirectStageWorkerService(session)
            if await direct.is_direct(task):
                identity = await direct_revocation_identity(session, task)
                if identity is None:
                    continue
                if actor and identity.actor_id != actor:
                    continue
                if project_id and identity.project_id != project_id:
                    continue
                if connection_id and connection_id not in identity.connection_ids:
                    continue
                from testing_agent.services.standalone_worker_service import StandaloneWorkerService

                standalone = StandaloneWorkerService(session)
                if await standalone.is_standalone(task):
                    await standalone.retire(
                        task, "操作人的项目访问或个人授权已失效，请配置本人授权后重新执行"
                    )
                else:
                    await direct.retire_authorization(task)
            # Unknown legacy AI entries are handled by the coordinated cutover,
            # and must never fall back to the retired ledger during revocation.
            continue
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
        if task.domain in {"api", "ui"}:
            notifications.append((task.domain, task.run_id, task.task_id))
    return notifications


async def notify_revoked_executions(tasks: list[tuple[str, str, str]]) -> None:
    """Publish only after the transaction that revoked execution commits."""
    from testing_agent.services.test_run_notifications import (
        notify_run_changed,
        notify_task_control,
    )

    for domain, run_id, task_id in tasks:
        await notify_run_changed(domain, run_id)
        await notify_task_control(task_id)

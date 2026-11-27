"""Business deletion commands; the caller authorizes access and commits once.

These commands own child-resource refusal and integration lifecycle fences.
Storage helpers only lock rows and remove owned data. No command deletes S3 objects.
"""

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent import models as m
from testing_agent.core.errors import AppError, ErrAiGenerateTaskRunRunning, ErrNotFound
from testing_agent.db.base import Base
from testing_agent.domain.resource_deletion import AUXILIARY_TASK_TYPES
from testing_agent.repositories.deletion import (
    delete_owned_data,
    lock_project_for_deletion,
    lock_resource_for_deletion,
)
from testing_agent.services.integration_lifecycle import guard_integrations, revoke_integrations


class ResourceDeletion(Protocol):
    async def delete(self, session: AsyncSession, resource: Base) -> None: ...


class SqlResourceDeletion:
    async def delete(self, session: AsyncSession, resource: Base) -> None:
        await delete_resource(session, resource)


async def delete_resource(session: AsyncSession, obj: Base) -> None:
    """Delete an authorized entity and its owned records, without committing."""
    if isinstance(obj, (m.Bug, m.Project, m.SharedService)):
        project_id = obj.project_id
        await lock_project_for_deletion(session, project_id)
        filters = {"project_id": project_id}
        if isinstance(obj, m.Bug):
            filters["bug_id"] = obj.bug_id
        elif isinstance(obj, m.SharedService):
            filters["service_id"] = obj.service_id
        await guard_integrations(session, **filters)
        await revoke_integrations(session, **filters)
    if not await lock_resource_for_deletion(session, obj):
        raise ErrNotFound()
    await _blockers(session, obj)

    await delete_owned_data(session, obj)


async def _reject_running_generation_tasks(session, requirement: m.Requirement) -> None:
    """A requirement owns its generation tasks, so none of them may still be running."""
    task_ids = list(
        await session.scalars(
            select(m.AiGenerateTask.task_id)
            .where(m.AiGenerateTask.requirement_id == requirement.requirement_id)
            .with_for_update()
        )
    )
    if not task_ids:
        return
    active_stage = await session.scalar(
        select(m.AiGenerationStage.id)
        .where(
            m.AiGenerationStage.task_id.in_(task_ids),
            m.AiGenerationStage.active_attempt_id.is_not(None),
        )
        .limit(1)
        .with_for_update()
    )
    if active_stage:
        raise ErrAiGenerateTaskRunRunning()


async def _blockers(session, obj):
    """Use locking reads so MySQL REPEATABLE READ cannot hide newly committed children."""
    if isinstance(obj, m.Requirement):
        await _reject_running_generation_tasks(session, obj)
    checks = []
    if isinstance(obj, m.Project):
        checks += [
            (m.Sprint, m.Sprint.project_id == obj.project_id, "迭代"),
            (m.ApiEnvironment, m.ApiEnvironment.project_id == obj.project_id, "测试环境"),
            (m.ProjectSkillSpace, m.ProjectSkillSpace.project_id == obj.project_id, "项目技能"),
            (m.SharedService, m.SharedService.project_id == obj.project_id, "项目共享服务"),
            (m.SoftwareRepository, m.SoftwareRepository.project_id == obj.project_id, "软件仓库"),
            (m.ApiCollection, m.ApiCollection.project_id == obj.project_id, "API 测试集"),
            (m.UiTestSuite, m.UiTestSuite.project_id == obj.project_id, "UI 测试集"),
            (m.PerfSuite, m.PerfSuite.project_id == obj.project_id, "性能测试集"),
            (m.PerfCase, m.PerfCase.project_id == obj.project_id, "性能用例"),
            (
                m.MonitoringConnection,
                m.MonitoringConnection.project_id == obj.project_id,
                "监控接入",
            ),
        ]
    elif isinstance(obj, m.Sprint):
        checks += [
            (m.Requirement, m.Requirement.sprint_id == obj.sprint_id, "需求"),
            (m.TestOrder, m.TestOrder.sprint_id == obj.sprint_id, "测试单"),
        ]
    elif isinstance(obj, m.Requirement):
        checks.append(
            (
                m.FunctionTestSuite,
                m.FunctionTestSuite.requirement_id == obj.requirement_id,
                "功能测试集",
            )
        )
    elif isinstance(obj, m.FunctionTestSuite):
        checks.append((m.FunctionTestCase, m.FunctionTestCase.suite_id == obj.suite_id, "测试用例"))
    elif isinstance(obj, m.UiTestSuite):
        checks.append((m.UiTestCase, m.UiTestCase.suite_id == obj.suite_id, "测试用例"))
    elif isinstance(obj, m.ApiCollection):
        checks.append((m.ApiCase, m.ApiCase.collection_id == obj.collection_id, "测试用例"))

    for model, kind, key in (
        (m.Project, "project", "project_id"),
        (m.Sprint, "sprint", "sprint_id"),
        (m.Requirement, "requirement", "requirement_id"),
    ):
        if isinstance(obj, model):
            value = getattr(obj, key)
            if not isinstance(obj, m.Requirement):
                # 需求的生成任务随需求一并删除，不算独立子资源。
                checks.append(
                    (
                        m.AiGenerateTask,
                        (getattr(m.AiGenerateTask, key) == value)
                        & (~m.AiGenerateTask.task_type.in_(AUXILIARY_TASK_TYPES)),
                        "AI 任务",
                    )
                )
            checks.append(
                (
                    m.ResourceBinding,
                    (m.ResourceBinding.local_resource_type == kind)
                    & (m.ResourceBinding.local_resource_id == value),
                    "资源绑定",
                )
            )
    blockers = []
    for child_model, condition, label in checks:
        ids = list(
            await session.scalars(
                select(child_model.__table__.c.id).where(condition).with_for_update()
            )
        )
        if ids:
            blockers.append(
                {"resource": child_model.__tablename__, "name": label, "count": len(ids)}
            )
    if blockers:
        detail = "、".join(f"{item['count']} 个{item['name']}" for item in blockers)
        raise AppError(409, f"请先删除子资源：{detail}", 409, {"blockers": blockers})

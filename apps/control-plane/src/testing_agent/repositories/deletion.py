"""Hard deletion: explicit business children block; owned implementation data is removed.

The caller authorizes access and commits the transaction. Files are removed only
following a successful commit; a rollback never removes a file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, event, or_, select
from sqlalchemy.orm import Session

from testing_agent import models as m
from testing_agent.core.errors import AppError, ErrNotFound

logger = logging.getLogger(__name__)
_FILE_QUEUE = "hard_delete_files"
# 非需求域 AI 任务只是派生产物的容器，随所属项目/迭代/测试单一起清理，不作为删除阻塞。
AUXILIARY_TASK_TYPES = ("test_report_generate", "test_order_graph")


@event.listens_for(Session, "after_commit")
def _remove_files(session):
    for filename in session.info.pop(_FILE_QUEUE, set()):
        try:
            Path(filename).unlink(missing_ok=True)
        except OSError:
            logger.exception("Unable to remove deleted resource file: %s", filename)


@event.listens_for(Session, "after_rollback")
def _keep_files(session):
    session.info.pop(_FILE_QUEUE, None)


def _file(session, filename):
    if filename:
        session.info.setdefault(_FILE_QUEUE, set()).add(filename)


async def _erase(session, model, *conditions):
    await session.execute(delete(model).where(*conditions))


async def _blockers(session, obj):
    """Use locking reads so MySQL REPEATABLE READ cannot hide newly committed children."""
    checks = []
    if isinstance(obj, m.Project):
        checks += [
            (m.Sprint, m.Sprint.project_id == obj.project_id, "迭代"),
            (m.ApiEnvironment, m.ApiEnvironment.project_id == obj.project_id, "API 环境"),
            (m.ProjectSkillSpace, m.ProjectSkillSpace.project_id == obj.project_id, "项目技能"),
            (m.SharedService, m.SharedService.project_id == obj.project_id, "项目共享服务"),
        ]
    elif isinstance(obj, m.Sprint):
        checks += [
            (m.Requirement, m.Requirement.sprint_id == obj.sprint_id, "需求"),
            (m.TestOrder, m.TestOrder.sprint_id == obj.sprint_id, "测试单"),
        ]
    elif isinstance(obj, m.Requirement):
        checks += [
            (model, model.requirement_id == obj.requirement_id, label)
            for model, label in (
                (m.FunctionTestSuite, "功能测试集"),
                (m.ApiCollection, "API 集合"),
                (m.UiTestSuite, "UI 测试集"),
            )
        ]
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
    for model, condition, label in checks:
        ids = list(await session.scalars(select(model.id).where(condition).with_for_update()))
        if ids:
            blockers.append({"resource": model.__tablename__, "name": label, "count": len(ids)})
    if blockers:
        detail = "、".join(f"{item['count']} 个{item['name']}" for item in blockers)
        raise AppError(409, f"请先删除子资源：{detail}", 409, {"blockers": blockers})


async def _workers(session, domain, run_ids):
    if run_ids:
        await _erase(
            session, m.WorkerTask, m.WorkerTask.domain == domain, m.WorkerTask.run_id.in_(run_ids)
        )


async def _api_runs(session, condition):
    ids = list(
        await session.scalars(select(m.ApiCaseRun.run_id).where(condition).with_for_update())
    )
    if ids:
        await _workers(session, "api", ids)
        await _erase(session, m.ApiCollectionRunItem, m.ApiCollectionRunItem.case_run_id.in_(ids))
        await _erase(session, m.ApiCaseRun, m.ApiCaseRun.run_id.in_(ids))


async def _api_collection_runs(session, condition):
    ids = list(
        await session.scalars(
            select(m.ApiCollectionRun.collection_run_id).where(condition).with_for_update()
        )
    )
    if ids:
        await _workers(session, "api", ids)
        await _erase(
            session, m.ApiCollectionRunItem, m.ApiCollectionRunItem.collection_run_id.in_(ids)
        )
        await _api_runs(session, m.ApiCaseRun.collection_run_id.in_(ids))
        await _erase(session, m.ApiCollectionRun, m.ApiCollectionRun.collection_run_id.in_(ids))


async def _ui_suite_runs(session, condition):
    ids = list(
        await session.scalars(
            select(m.UiTestSuiteRun.suite_run_id).where(condition).with_for_update()
        )
    )
    if ids:
        await _workers(session, "ui", ids)
        await _erase(session, m.UiTestSuiteRunItem, m.UiTestSuiteRunItem.suite_run_id.in_(ids))
        await _erase(session, m.UiTestSuiteRun, m.UiTestSuiteRun.suite_run_id.in_(ids))


async def _ai_run_children(session, run_ids):
    """Erase what a set of AI runs owns; the run rows themselves are deleted by the caller."""
    if not run_ids:
        return
    stages = select(m.AiGenerateRunStage.id).where(m.AiGenerateRunStage.run_id.in_(run_ids))
    await _workers(session, "ai", run_ids)
    # Imports reference attempts, so remove them before stage/attempt cleanup.
    await _erase(session, m.AiGenerateRunImport, m.AiGenerateRunImport.run_id.in_(run_ids))
    await _erase(session, m.AiGenerateStageAttempt, m.AiGenerateStageAttempt.stage_id.in_(stages))
    await _erase(session, m.AiGenerateRunStage, m.AiGenerateRunStage.run_id.in_(run_ids))


async def _ai_runs(session, condition):
    ids = list(
        await session.scalars(select(m.AiGenerateTaskRun.run_id).where(condition).with_for_update())
    )
    await _ai_run_children(session, ids)
    if ids:
        await _erase(session, m.AiGenerateTaskRun, m.AiGenerateTaskRun.run_id.in_(ids))


async def delete_resource(session, obj):
    """Delete an authorized entity and its owned records, without committing."""
    model = type(obj)
    locked = await session.scalar(select(model).where(model.id == obj.id).with_for_update())
    if locked is None:
        raise ErrNotFound
    await _blockers(session, obj)

    if isinstance(obj, m.ApiCase):
        # Aggregate snapshots/counters cannot be kept after removing one of their cases.
        containing_runs = select(m.ApiCollectionRunItem.collection_run_id).where(
            m.ApiCollectionRunItem.case_id == obj.case_id
        )
        case_runs = select(m.ApiCaseRun.collection_run_id).where(
            m.ApiCaseRun.case_id == obj.case_id
        )
        await _api_collection_runs(
            session,
            or_(
                m.ApiCollectionRun.collection_run_id.in_(containing_runs),
                m.ApiCollectionRun.collection_run_id.in_(case_runs),
            ),
        )
        await _api_runs(session, m.ApiCaseRun.case_id == obj.case_id)
        for child in (m.ApiCollectionRunItem, m.ApiAssertRule, m.ApiExtractRule):
            await _erase(session, child, child.case_id == obj.case_id)
    elif isinstance(obj, m.ApiCollection):
        await _api_collection_runs(session, m.ApiCollectionRun.collection_id == obj.collection_id)
        await _api_runs(session, m.ApiCaseRun.collection_id == obj.collection_id)
    elif isinstance(obj, m.ApiEnvironment):
        await _api_collection_runs(session, m.ApiCollectionRun.environment_id == obj.environment_id)
        await _api_runs(session, m.ApiCaseRun.environment_id == obj.environment_id)
        await _erase(
            session, m.ApiEnvironmentVar, m.ApiEnvironmentVar.environment_id == obj.environment_id
        )
    elif isinstance(obj, m.UiTestCase):
        containing_runs = select(m.UiTestSuiteRunItem.suite_run_id).where(
            m.UiTestSuiteRunItem.case_id == obj.case_id
        )
        await _ui_suite_runs(session, m.UiTestSuiteRun.suite_run_id.in_(containing_runs))
        ids = list(
            await session.scalars(
                select(m.UiTestCaseRun.run_id)
                .where(m.UiTestCaseRun.case_id == obj.case_id)
                .with_for_update()
            )
        )
        await _workers(session, "ui", ids)
        await _erase(session, m.UiTestSuiteRunItem, m.UiTestSuiteRunItem.case_id == obj.case_id)
        await _erase(session, m.UiTestCaseRun, m.UiTestCaseRun.case_id == obj.case_id)
    elif isinstance(obj, m.UiTestSuite):
        await _ui_suite_runs(session, m.UiTestSuiteRun.suite_id == obj.suite_id)
    elif isinstance(obj, m.TestOrder):
        await _erase(session, m.TestOrderEntry, m.TestOrderEntry.order_id == obj.order_id)
        graph_tasks = list(
            await session.scalars(
                select(m.AiGenerateTask).where(
                    m.AiGenerateTask.order_id == obj.order_id,
                    m.AiGenerateTask.task_type == "test_order_graph",
                )
            )
        )
        for graph_task in graph_tasks:
            await delete_resource(session, graph_task)
    elif isinstance(obj, m.FunctionTestCase):
        # 引用了该用例的执行条目随用例一起删除（条目只按业务键引用用例，没有外键）。
        await _erase(session, m.TestOrderEntry, m.TestOrderEntry.case_id == obj.case_id)
    elif isinstance(obj, m.AiGenerateTaskRun):
        await _ai_run_children(session, [obj.run_id])
    elif isinstance(obj, m.AiGenerateTask):
        await _ai_runs(session, m.AiGenerateTaskRun.task_id == obj.task_id)
        archives = list(
            await session.scalars(
                select(m.AiGenerateTaskSourceArchive).where(
                    m.AiGenerateTaskSourceArchive.task_id == obj.task_id
                )
            )
        )
        for archive in archives:
            _file(session, archive.storage_path)
        await _erase(
            session,
            m.AiGenerateTaskSourceArchive,
            m.AiGenerateTaskSourceArchive.task_id == obj.task_id,
        )
    elif isinstance(obj, m.IntegrationConnection):
        await _erase(
            session,
            m.ServiceAuthorization,
            m.ServiceAuthorization.connection_id == obj.connection_id,
        )
    elif isinstance(obj, m.SharedService):
        connections = list(
            await session.scalars(
                select(m.IntegrationConnection)
                .join(
                    m.ServiceAuthorization,
                    m.ServiceAuthorization.connection_id == m.IntegrationConnection.connection_id,
                )
                .where(m.ServiceAuthorization.service_id == obj.service_id)
            )
        )
        for connection in connections:
            await delete_resource(session, connection)
        await _erase(
            session, m.ServiceAuthorization, m.ServiceAuthorization.service_id == obj.service_id
        )
    elif isinstance(obj, m.Requirement):
        _file(session, obj.document_storage_path)
    elif isinstance(obj, m.ProjectSkillSpace):
        _file(session, obj.storage_path)

    if isinstance(obj, (m.Project, m.Sprint)):
        key = "project_id" if isinstance(obj, m.Project) else "sprint_id"
        value = getattr(obj, key)
        # Auxiliary AI tasks are internal run containers with no independent CRUD UI.
        auxiliaries = list(
            await session.scalars(
                select(m.AiGenerateTask).where(
                    getattr(m.AiGenerateTask, key) == value,
                    m.AiGenerateTask.task_type.in_(AUXILIARY_TASK_TYPES),
                )
            )
        )
        for auxiliary in auxiliaries:
            await delete_resource(session, auxiliary)
        if isinstance(obj, m.Sprint):
            await _erase(session, m.SprintDailyMetrics, m.SprintDailyMetrics.sprint_id == value)
        else:
            # Personal credentials and membership are implementation data of the project.
            connections = list(
                await session.scalars(
                    select(m.IntegrationConnection).where(
                        m.IntegrationConnection.project_id == value
                    )
                )
            )
            for connection in connections:
                await delete_resource(session, connection)
            await _erase(session, m.ProjectMember, m.ProjectMember.project_id == value)
    await session.delete(obj)
    await session.flush()

"""Owned-record storage cleanup; business deletion policy lives in the service layer.

The caller authorizes access and commits the transaction. S3 objects are retained
by the unified file lifecycle; resource deletion never touches historical local paths.
"""

from __future__ import annotations

from sqlalchemy import delete, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent import models as m
from testing_agent.core.errors import ErrNotFound
from testing_agent.db.base import Base
from testing_agent.domain.resource_deletion import AUXILIARY_TASK_TYPES


async def _erase(session, model, *conditions):
    await session.execute(delete(model).where(*conditions))


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


async def delete_owned_data(session: AsyncSession, obj: Base) -> None:
    """Erase owned storage after the caller locks and authorizes the root resource.

    Recursive children are implementation data (AI containers or personal
    connection rows), never business lifecycle dispatches.
    """
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
            await _delete_owned_child(session, graph_task)
    elif isinstance(obj, m.FunctionTestCase):
        # 引用了该用例的执行条目随用例一起删除（条目只按业务键引用用例，没有外键）。
        await _erase(session, m.TestOrderEntry, m.TestOrderEntry.case_id == obj.case_id)
    elif isinstance(obj, m.AiGenerateTaskRun):
        await _ai_run_children(session, [obj.run_id])
    elif isinstance(obj, m.AiGenerateTask):
        await _ai_runs(session, m.AiGenerateTaskRun.task_id == obj.task_id)
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
            await _delete_owned_child(session, connection)
        await _erase(
            session, m.ServiceAuthorization, m.ServiceAuthorization.service_id == obj.service_id
        )

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
            await _delete_owned_child(session, auxiliary)
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
                await _delete_owned_child(session, connection)
            await _erase(session, m.ProjectMember, m.ProjectMember.project_id == value)
    await session.delete(obj)
    await session.flush()


async def lock_project_for_deletion(session: AsyncSession, project_id: str) -> None:
    await session.scalar(
        select(m.Project).where(m.Project.project_id == project_id).with_for_update()
    )


async def lock_resource_for_deletion(session: AsyncSession, obj: Base) -> bool:
    model = type(obj)
    mapper = inspect(obj).mapper
    row = await session.scalar(
        select(model)
        .where(
            *(
                column == getattr(obj, mapper.get_property_by_column(column).key)
                for column in mapper.primary_key
            )
        )
        .with_for_update()
    )
    return row is not None


async def _delete_owned_child(session: AsyncSession, obj: Base) -> None:
    if not isinstance(obj, (m.AiGenerateTask, m.IntegrationConnection)):
        raise ValueError("Only owned implementation records may use recursive storage deletion")
    if not await lock_resource_for_deletion(session, obj):
        raise ErrNotFound()
    await delete_owned_data(session, obj)

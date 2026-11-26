"""Owned-record storage cleanup; business deletion policy lives in the service layer.

The caller authorizes access and commits the transaction. S3 objects are retained
by the unified file lifecycle; resource deletion never touches historical local paths.
"""

from __future__ import annotations

from sqlalchemy import delete, inspect, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent import models as m
from testing_agent.core.errors import ErrNotFound
from testing_agent.db.base import Base
from testing_agent.domain.resource_deletion import AUXILIARY_TASK_TYPES
from testing_agent.repositories.generation_current_chain import delete_chain_storage_for_task
from testing_agent.repositories.generation_schema import candidate_schema_installed


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


async def _perf_runs(session, condition):
    ids = list(await session.scalars(select(m.PerfRun.run_id).where(condition).with_for_update()))
    if ids:
        await _workers(session, "perf", ids)
        await _erase(session, m.PerfRun, m.PerfRun.run_id.in_(ids))


async def _perf_suite_runs(session, condition):
    ids = list(
        await session.scalars(
            select(m.PerfSuiteRun.suite_run_id).where(condition).with_for_update()
        )
    )
    if ids:
        await _erase(session, m.PerfSuiteRunItem, m.PerfSuiteRunItem.suite_run_id.in_(ids))
        await _erase(session, m.PerfSuiteRun, m.PerfSuiteRun.suite_run_id.in_(ids))


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
    elif isinstance(obj, m.PerfSuite):
        case_ids = select(m.PerfCase.case_id).where(m.PerfCase.suite_id == obj.suite_id)
        await _perf_runs(session, m.PerfRun.case_id.in_(case_ids))
        await _perf_suite_runs(session, m.PerfSuiteRun.suite_id == obj.suite_id)
        # Delete cases explicitly instead of relying on the FK cascade so SQLite
        # test databases and MySQL behave identically.
        await _erase(session, m.PerfCase, m.PerfCase.suite_id == obj.suite_id)
    elif isinstance(obj, m.PerfCase):
        containing_runs = select(m.PerfSuiteRunItem.suite_run_id).where(
            m.PerfSuiteRunItem.case_id == obj.case_id
        )
        await _perf_suite_runs(session, m.PerfSuiteRun.suite_run_id.in_(containing_runs))
        await _perf_runs(session, m.PerfRun.case_id == obj.case_id)
    elif isinstance(obj, m.MonitoringConnection):
        # 运行记录已冻结接入快照，删除接入不影响历史运行。
        pass
    elif isinstance(obj, m.TestOrderEntry):
        await _entry_visualizations(session, m.TestOrderEntry.entry_id == obj.entry_id)
    elif isinstance(obj, m.TestOrder):
        await _entry_visualizations(session, m.TestOrderEntry.order_id == obj.order_id)
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
        await _entry_visualizations(session, m.TestOrderEntry.case_id == obj.case_id)
        # 引用了该用例的执行条目随用例一起删除（条目只按业务键引用用例，没有外键）。
        await _erase(session, m.TestOrderEntry, m.TestOrderEntry.case_id == obj.case_id)
    elif isinstance(obj, m.Requirement):
        # API/UI 测试集是项目级资产；需求删除只解除关联，不删除资产。
        # 显式更新同时覆盖未启用 SQLite 外键的历史测试库。
        await session.execute(
            update(m.ApiCollection)
            .where(m.ApiCollection.requirement_id == obj.requirement_id)
            .values(requirement_id=None)
        )
        await session.execute(
            update(m.UiTestSuite)
            .where(m.UiTestSuite.requirement_id == obj.requirement_id)
            .values(requirement_id=None)
        )
    elif isinstance(obj, m.AiGenerateTask):
        if await candidate_schema_installed(session):
            await delete_chain_storage_for_task(session, task_id=obj.task_id)
        attempt_ids = list(
            await session.scalars(
                select(m.AiGenerationAttempt.id)
                .join(m.AiGenerationStage, m.AiGenerationStage.id == m.AiGenerationAttempt.stage_id)
                .where(m.AiGenerationStage.task_id == obj.task_id)
                .with_for_update()
            )
        )
        await _workers(session, "ai", attempt_ids)
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
    if isinstance(obj, m.Requirement):
        # 生成任务是需求自己的设计容器：随需求一并清理，候选与阶段内容按外键级联。
        # 正式资产和自包含导入回执不在此删除。
        tasks = list(
            await session.scalars(
                select(m.AiGenerateTask).where(
                    m.AiGenerateTask.requirement_id == obj.requirement_id
                )
            )
        )
        for task in tasks:
            await _delete_owned_child(session, task)
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


async def _entry_visualizations(session: AsyncSession, condition) -> None:
    # Serialize new bindings with dispatch and use a current read under MySQL RR.
    entries = list(
        await session.scalars(
            select(m.TestOrderEntry.entry_id)
            .where(condition)
            .order_by(m.TestOrderEntry.entry_id)
            .with_for_update()
        )
    )
    tasks = list(
        await session.scalars(
            select(m.AiGenerateTask)
            .where(
                m.AiGenerateTask.task_type == "test_order_case_visualization",
                m.AiGenerateTask.execution_entry_id.in_(entries),
            )
            .order_by(m.AiGenerateTask.task_id)
            .with_for_update()
        )
    )
    for task in tasks:
        attempt_ids = list(
            await session.scalars(
                select(m.AiGenerationAttempt.id)
                .join(
                    m.AiGenerationStage,
                    m.AiGenerationStage.id == m.AiGenerationAttempt.stage_id,
                )
                .where(m.AiGenerationStage.task_id == task.task_id)
            )
        )
        # Lock queue before attempts, matching completion instead of generic cleanup order.
        await _workers(session, "ai", attempt_ids)
        await _delete_owned_child(session, task)

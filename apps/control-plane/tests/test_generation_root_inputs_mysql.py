"""Current API roots recheck associations after acquiring MySQL locks."""

import asyncio

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.domain.generation_root_fingerprints import IncompleteRootInput
from testing_agent.models import (
    AiGenerateTask,
    ApiInterface,
    Base,
    FunctionTestCase,
    FunctionTestSuite,
    SoftwareRepository,
)
from testing_agent.repositories.generation_root_inputs import (
    lock_api_interface_root,
    lock_ui_repository_cases_root,
)


def test_api_interface_moved_during_lock_is_not_mistaken_for_old_source(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        first = seed_row(
            connection, tables["software_repositories"], {"project_id": project["project_id"]}
        )
        second = seed_row(
            connection, tables["software_repositories"], {"project_id": project["project_id"]}
        )
        interface = seed_row(
            connection,
            tables["api_interfaces"],
            {"software_repository_id": first["software_repository_id"]},
        )
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "api_case_generate",
                "interface_ids_json": [interface["interface_id"]],
            },
        )

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        discovered = asyncio.Event()

        @sa.event.listens_for(engine.sync_engine, "after_cursor_execute")
        def signal(_conn, _cursor, statement, _params, _context, _many):
            if (
                "api_interfaces.interface_id" in statement
                and "api_interfaces.software_repository_id" in statement
                and "FOR UPDATE" not in statement.upper()
            ):
                discovered.set()

        try:
            async with factory() as editor, factory() as reader:
                await editor.scalars(
                    sa.select(SoftwareRepository)
                    .where(
                        SoftwareRepository.software_repository_id.in_(
                            [first["software_repository_id"], second["software_repository_id"]]
                        )
                    )
                    .order_by(SoftwareRepository.software_repository_id)
                    .with_for_update()
                )
                task_row = await reader.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
                )
                assert task_row
                verifying = asyncio.create_task(lock_api_interface_root(reader, task=task_row))
                await asyncio.wait_for(discovered.wait(), timeout=10)
                await editor.execute(
                    sa.update(ApiInterface)
                    .where(ApiInterface.interface_id == interface["interface_id"])
                    .values(software_repository_id=second["software_repository_id"])
                )
                await editor.commit()
                with pytest.raises(IncompleteRootInput, match="changed"):
                    await asyncio.wait_for(verifying, timeout=10)
                await reader.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_ui_selected_case_moved_during_lock_is_not_mistaken_for_old_source(mysql):  # noqa: F811
    tables = Base.metadata.tables
    with mysql.begin() as connection:
        project = seed_row(connection, tables["projects"])
        sprint = seed_row(connection, tables["sprints"], {"project_id": project["project_id"]})
        requirement = seed_row(
            connection, tables["requirements"], {"sprint_id": sprint["sprint_id"]}
        )
        first = seed_row(
            connection,
            tables["function_test_suites"],
            {"requirement_id": requirement["requirement_id"]},
        )
        second = seed_row(
            connection,
            tables["function_test_suites"],
            {"requirement_id": requirement["requirement_id"]},
        )
        case = seed_row(connection, tables["function_test_cases"], {"suite_id": first["suite_id"]})
        task = seed_row(
            connection,
            tables["ai_generate_tasks"],
            {
                "project_id": project["project_id"],
                "sprint_id": sprint["sprint_id"],
                "requirement_id": requirement["requirement_id"],
                "task_type": "ui_case_generate",
            },
        )
    frozen_source = {
        "taskId": task["task_id"],
        "requirementId": requirement["requirement_id"],
        "uiSourceBatchId": "batch",
        "sourceRepository": {
            "repositoryId": "repo",
            "instanceUrl": "https://git.example",
            "pathWithNamespace": "group/repo",
            "branch": "main",
            "commit": "fixed",
        },
        "functionalCases": [{"caseId": case["case_id"]}],
    }

    async def exercise():
        engine = create_async_engine(mysql.url.set(drivername="mysql+asyncmy"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        discovered = asyncio.Event()

        @sa.event.listens_for(engine.sync_engine, "after_cursor_execute")
        def signal(_conn, _cursor, statement, _params, _context, _many):
            if (
                "function_test_cases.case_id" in statement
                and "function_test_cases.suite_id" in statement
                and "FOR UPDATE" not in statement.upper()
            ):
                discovered.set()

        try:
            async with factory() as editor, factory() as reader:
                await editor.scalars(
                    sa.select(FunctionTestSuite)
                    .where(FunctionTestSuite.suite_id.in_([first["suite_id"], second["suite_id"]]))
                    .order_by(FunctionTestSuite.suite_id)
                    .with_for_update()
                )
                task_row = await reader.scalar(
                    sa.select(AiGenerateTask).where(AiGenerateTask.task_id == task["task_id"])
                )
                assert task_row
                verifying = asyncio.create_task(
                    lock_ui_repository_cases_root(
                        reader, task=task_row, frozen_source=frozen_source
                    )
                )
                await asyncio.wait_for(discovered.wait(), timeout=10)
                await editor.execute(
                    sa.update(FunctionTestCase)
                    .where(FunctionTestCase.case_id == case["case_id"])
                    .values(suite_id=second["suite_id"])
                )
                await editor.commit()
                with pytest.raises(IncompleteRootInput, match="changed"):
                    await asyncio.wait_for(verifying, timeout=10)
                await reader.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())

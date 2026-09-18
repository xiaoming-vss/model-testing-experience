from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_function_confirmed_import import FunctionImportRepository, approved_run, import_client

from testing_agent.core.errors import AppError
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.function_generate_import import import_function_run


@pytest.mark.asyncio
async def test_concurrent_suite_name_conflict_rolls_back_autoflush_and_allows_retry():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(FunctionTestSuite.__table__.create)
            await connection.run_sync(FunctionTestCase.__table__.create)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            existing_suite = FunctionTestSuite(
                suite_id="existing-search",
                requirement_id="requirement-1",
                name="数据检索",
                description="",
            )
            session.add(existing_suite)
            await session.commit()
            run = approved_run()
            run.result_yaml = """cases:
  - module: New module
    title: New case
  - module: 数据检索
    title: Search case
"""
            repository = AiGenerateTaskRepository(session)
            # Simulate a concurrent insert after the name pre-check.
            repository.get_function_suite_by_requirement_and_name = AsyncMock(return_value=None)
            repository.get_run_for_update = AsyncMock(return_value=run)
            repository.refresh = AsyncMock()
            service = SimpleNamespace(
                repository=repository,
                owned_run=AsyncMock(return_value=run),
                ensure_requirement_access=AsyncMock(),
            )

            with pytest.raises(AppError) as error:
                await import_function_run(service, run.run_id, False, "user-1")

            assert error.value.http_code == 409
            assert error.value.code == 3202
            assert "名称已被占用" in error.value.message
            assert isinstance(error.value.__cause__, IntegrityError)
            assert run.review_status == "approved"
            assert run.import_status == "pending"
            assert run.imported_targets == []
            assert run.imported_at is None
            assert list(await session.scalars(select(FunctionTestCase))) == []
            suites = list(await session.scalars(select(FunctionTestSuite)))
            assert [suite.suite_id for suite in suites] == ["existing-search"]

            run.result_yaml = run.result_yaml.replace("数据检索", "新数据检索")
            result = await import_function_run(service, run.run_id, False, "user-1")
            assert result["run"]["importStatus"] == "imported"
            assert len(list(await session.scalars(select(FunctionTestCase)))) == 2
    finally:
        await engine.dispose()


@pytest.mark.parametrize("failure_at", ["autoflush", "commit"])
@pytest.mark.parametrize("suite_conflict", [True, False])
def test_mysql_import_translates_only_suite_name_conflicts(failure_at, suite_conflict):
    key = "uk_function_suite_requirement_name" if suite_conflict else "unrelated_key"
    failure = IntegrityError(
        "INSERT", {}, RuntimeError(1062, f"Duplicate entry for key 'function_test_suites.{key}'")
    )
    repository = FunctionImportRepository()
    if failure_at == "autoflush":
        repository.max_function_case_order_by_suite = AsyncMock(side_effect=failure)
    else:
        repository.commit = AsyncMock(side_effect=failure)
    client = import_client(repository)

    if suite_conflict:
        response = client.post(
            "/v1/function-case-generate-task-runs/run-1/import",
            json={"confirmOverwrite": True},
        )
        assert response.status_code == 409
        assert response.json()["code"] == 3202
    else:
        with pytest.raises(IntegrityError):
            client.post(
                "/v1/function-case-generate-task-runs/run-1/import",
                json={"confirmOverwrite": True},
            )
    assert repository.rollbacks == 1
    assert repository.run.import_status == "pending"
    assert repository.run.imported_targets == []
    assert repository.run.imported_at is None

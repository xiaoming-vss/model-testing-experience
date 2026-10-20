import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from support.execution_writer import MemoryExecutionWriter
from test_function_confirmed_import import approved_run

from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.function_generate_import import import_function_run


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_id", ["", "candidate-new", "occupied-id"])
async def test_import_candidate_identity_with_real_repository(candidate_id: str):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(FunctionTestSuite.__table__.create)
            await connection.run_sync(FunctionTestCase.__table__.create)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(
                FunctionTestSuite(
                    suite_id="other-suite", requirement_id="other-requirement", name="Other"
                )
            )
            session.add(
                FunctionTestCase(
                    case_id="occupied-id", suite_id="other-suite", title="Existing case"
                )
            )
            await session.commit()
            run = approved_run()
            run.result_yaml = json.dumps(
                {"cases": [{"case_id": candidate_id, "module": "New", "title": "New case"}]}
            )
            repository = AiGenerateTaskRepository(session)
            repository.refresh = AsyncMock()
            service = SimpleNamespace(
                repository=repository,
                execution=MemoryExecutionWriter(),
                owned_run=AsyncMock(return_value=run),
                ensure_requirement_access=AsyncMock(),
            )

            result = await import_function_run(service, run.run_id, False, "user-1")

            assert result["run"]["importStatus"] == "imported"
            cases = list(await session.scalars(select(FunctionTestCase)))
            assert len(cases) == 2
            imported = next(case for case in cases if case.title == "New case")
            assert imported.case_id
            if candidate_id == "candidate-new":
                assert imported.case_id == candidate_id
            else:
                assert imported.case_id != candidate_id
            original = next(case for case in cases if case.case_id == "occupied-id")
            assert original.title == "Existing case"
            assert original.suite_id == "other-suite"
    finally:
        await engine.dispose()

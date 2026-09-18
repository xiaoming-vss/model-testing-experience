
import pytest
from test_ai_execution_storage import AsyncSessionAdapter
from test_ai_execution_storage import db as db
from test_function_case_content import prepare

from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.function_test_suite import FunctionTestSuiteRepository
from testing_agent.services.function_test_suite import FunctionTestSuiteService


@pytest.mark.asyncio
async def test_suite_counts_include_only_own_cases_and_refresh_after_delete(db):
    prepare(db)
    db.add(FunctionTestSuite(suite_id="empty", requirement_id="req", name="空测试集"))
    db.add(FunctionTestSuite(suite_id="other-suite", requirement_id="req", name="其他测试集"))
    db.flush()
    first = FunctionTestCase(case_id="first", suite_id="function-suite", title="有效")
    db.add_all(
        [
            first,
            FunctionTestCase(case_id="elsewhere", suite_id="other-suite", title="其他测试集"),
        ]
    )
    db.commit()
    service = FunctionTestSuiteService(FunctionTestSuiteRepository(AsyncSessionAdapter(db)))
    listing = await service.list("u1", "req")
    counts = {item["suiteId"]: item["caseCount"] for item in listing["items"]}
    assert counts == {"function-suite": 1, "empty": 0, "other-suite": 1}
    assert (await service.get("u1", "function-suite"))["caseCount"] == 1
    db.delete(first)
    db.commit()
    assert (await service.get("u1", "function-suite"))["caseCount"] == 0

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_ai_execution_storage import AsyncSessionAdapter
from test_ai_execution_storage import db as db
from test_ui_run_scope import seed
from test_worker_queue_storage import row

from testing_agent.domain.function_case_content import CaseContent, from_legacy
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.schemas.function_test_case import FunctionCaseRequest
from testing_agent.services.function_test_case import FunctionTestCaseService


def test_numbered_pairs_and_unmatched_text_conversion():
    assert from_legacy("1. 条件甲\n2. 条件乙", "1. 打开\n2. 保存", "1. 显示\n2. 成功") == {
        "preconditions": ["条件甲", "条件乙"],
        "steps": [{"action": "打开", "expected": "显示"}, {"action": "保存", "expected": "成功"}],
    }
    steps, expected = "1. 打开\n2. 保存", "1. 最终成功"
    assert from_legacy("", steps, expected)["steps"] == [{"action": steps, "expected": expected}]
    assert (
        from_legacy("", "一段多行\n操作文字", "完整预期")["steps"][0]["action"]
        == "一段多行\n操作文字"
    )


@pytest.mark.parametrize(
    "content",
    [
        {"preconditions": "text", "steps": []},
        {"preconditions": [], "steps": [{"action": "x"}]},
        {"preconditions": [], "steps": [{"action": 1, "expected": "x"}]},
        {"preconditions": [], "steps": [], "unknown": True},
    ],
)
def test_content_contract_rejects_invalid_shapes(content):
    with pytest.raises(ValidationError):
        CaseContent.model_validate(content)


def prepare(db):
    seed(db)
    FunctionTestSuite.__table__.create(db.get_bind(), checkfirst=True)
    FunctionTestCase.__table__.create(db.get_bind(), checkfirst=True)
    db.add(row(FunctionTestSuite, suite_id="function-suite", requirement_id="req"))
    db.commit()


@pytest.mark.asyncio
async def test_structured_create_edit_and_legacy_update(db):
    prepare(db)
    service = FunctionTestCaseService(FunctionTestCaseRepository(AsyncSessionAdapter(db)))
    content = {
        "preconditions": ["先登录"],
        "steps": [{"action": "打开\n保持多行", "expected": "可见"}],
    }
    response = await service.create(
        "u1", "function-suite", FunctionCaseRequest(title="结构用例", content=content)
    )
    assert response["content"] == content
    assert response["steps"] == "打开\n保持多行"
    content["steps"].append({"action": "提交", "expected": "成功"})
    updated = await service.update("u1", response["caseId"], {"content": content})
    assert updated["content"]["steps"][1]["expected"] == "成功"
    legacy = await service.update(
        "u1",
        response["caseId"],
        {
            "steps": "1. 新操作",
            "expectedResults": "1. 新预期",
        },
    )
    assert legacy["content"]["steps"] == [{"action": "新操作", "expected": "新预期"}]
    db.expunge_all()
    stored = db.scalar(select(FunctionTestCase))
    assert stored.content_json == legacy["content"]
    assert not {"preconditions", "steps", "expected_results"} & set(
        FunctionTestCase.__table__.columns.keys()
    )


@pytest.mark.asyncio
async def test_manual_case_creation_stores_a_platform_generated_identifier(db):
    prepare(db)
    service = FunctionTestCaseService(FunctionTestCaseRepository(AsyncSessionAdapter(db)))
    created = [
        await service.create("u1", "function-suite", FunctionCaseRequest(title=title))
        for title in ("人工用例甲", "人工用例乙")
    ]

    identifiers = [case["caseId"] for case in created]
    for identifier in identifiers:
        assert UUID(identifier).version == 4
    assert len(set(identifiers)) == 2

    db.expunge_all()
    stored = {case.title: case.case_id for case in db.scalars(select(FunctionTestCase))}
    assert stored == {"人工用例甲": identifiers[0], "人工用例乙": identifiers[1]}

    edited = await service.update("u1", identifiers[0], {"title": "人工用例甲（改）"})
    assert edited["caseId"] == identifiers[0]


@pytest.mark.asyncio
async def test_import_rejects_invalid_structured_body(db):
    from testing_agent.core.errors import AppError

    prepare(db)
    service = FunctionTestCaseService(FunctionTestCaseRepository(AsyncSessionAdapter(db)))
    with pytest.raises(AppError, match="正文格式不正确"):
        await service.import_cases(
            "u1",
            "function-suite",
            {
                "cases": [
                    {
                        "title": "无效",
                        "content": {"preconditions": "非数组", "steps": []},
                    }
                ]
            },
            None,
        )
    assert db.scalar(select(FunctionTestCase)) is None


@pytest.mark.asyncio
async def test_zentao_export_preserves_multiline_step_boundaries():
    from testing_agent.services.function_test_case import ZentaoFunctionCaseImportTarget

    sent = []

    class Client:
        async def create_test_cases(self, connection, payload):
            sent.append(payload)
            return {"items": [{"id": 1, "status": "success"}]}

    case = FunctionTestCase(
        case_id="multi",
        suite_id="suite",
        title="多行",
        content={
            "preconditions": ["已登录"],
            "steps": [
                {"action": "输入账号\n输入密码", "expected": "保持页面\n展示输入"},
                {"action": "提交", "expected": "成功"},
            ],
        },
    )
    service = FunctionTestCaseService(None, zentao_resource_client=Client())
    target = ZentaoFunctionCaseImportTarget(None, 1, 0, 2, 3, 4)
    await service.import_suite_cases_to_zentao("suite", [case], target)
    assert sent[0]["cases"][0]["steps"] == ["输入账号\n输入密码", "提交"]
    assert sent[0]["cases"][0]["expects"] == ["保持页面\n展示输入", "成功"]

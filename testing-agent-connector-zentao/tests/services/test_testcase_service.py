import pytest

from app.schemas.zentao.imports import ImportListQuery
from app.schemas.zentao.testcase import TestCaseBatchCreateRequest as BatchCreateCaseRequest
from app.schemas.zentao.testcase import normalize_case_steps
from app.services.zentao import ZentaoTestCaseService


@pytest.mark.parametrize("shape", ["dict", "list", "tuple"])
def test_case_steps_preserve_descriptions_and_expectations(shape: str) -> None:
    steps = [
        {"desc": "打开页面", "expect": "页面显示正常"},
        {"desc": "点击提交", "expect": "提交成功"},
    ]
    value = {"1": steps[0], "2": steps[1]} if shape == "dict" else steps
    if shape == "tuple":
        value = tuple(steps)
    assert normalize_case_steps(value) == (
        "1. 打开页面\n2. 点击提交",
        "1. 页面显示正常\n2. 提交成功",
    )


def test_empty_dictionary_steps_remain_empty() -> None:
    assert normalize_case_steps({}) == (None, None)


class FakeTestCaseClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []
        self.updated_payloads: list[tuple[int, dict[str, object]]] = []

    async def create_testcase(self, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append(payload)
        return {"status": "success", "id": 455 + len(self.payloads)}

    async def update_testcase(
        self,
        case_id: int,
        payload: dict[str, object],
    ) -> dict[str, object]:
        self.updated_payloads.append((case_id, payload))
        return {"status": "success"}

    async def list_execution_testcases(
        self,
        execution_id: int,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        assert execution_id in {3, 11}
        assert params in (
            {"browseType": "all", "recPerPage": 100, "pageID": 1},
            {"browseType": "all", "recPerPage": 1000, "pageID": 1},
        )
        if execution_id == 3:
            return {
                "status": "success",
                "total": "1",
                "testcases": [
                    {
                        "id": 1001,
                        "case": "123",
                        "status": "normal",
                    }
                ],
            }
        return {
            "status": "success",
            "total": "1",
            "testcases": [
                {
                    "id": 999,
                    "case": "123",
                    "status": "normal",
                    "lastRunDate": "2026-06-10 09:30:00",
                    "lastRunResult": "pass",
                }
            ],
        }

    async def get_testcase(self, case_id: int) -> dict[str, object]:
        assert case_id == 123
        return {
            "status": "success",
            "testcase": {
                "id": "123",
                "module": "Login Module",
                "title": "第二条测试用例",
                "precondition": "User is registered",
                "pri": "1",
                "type": "functional",
                "deleted": "0",
                "steps": [
                    {"desc": "Enter account and password", "expect": "Input succeeds"},
                    {"desc": "Click login", "expect": "Login succeeds"},
                ],
            },
        }


@pytest.mark.anyio
async def test_create_testcases_forwards_payloads_and_normalizes_result() -> None:
    testcase_client = FakeTestCaseClient()
    service = ZentaoTestCaseService(testcase_client=testcase_client)

    result = await service.create_testcases(
        BatchCreateCaseRequest(
            productID=1,
            project=2,
            execution=3,
            cases=[
                {
                    "title": "测试压敏模块显示是否正常",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "已进入压敏模块页面",
                    "steps": ["步骤1", "步骤2"],
                    "expects": ["期望1", "期望2"],
                },
                {
                    "title": "第二条测试用例",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "",
                    "steps": ["步骤A"],
                    "expects": ["期望A"],
                },
            ],
        )
    )

    assert testcase_client.payloads == [
        {
            "productID": 1,
            "title": "测试压敏模块显示是否正常",
            "module": 0,
            "story": 0,
            "pri": 3,
            "precondition": "已进入压敏模块页面",
            "steps": ["步骤1", "步骤2"],
            "expects": ["期望1", "期望2"],
            "stepType": ["step", "step"],
            "project": 2,
            "execution": 3,
        },
    ]
    assert testcase_client.updated_payloads == [
        (
            123,
            {
                "productID": 1,
                "title": "第二条测试用例",
                "module": 0,
                "story": 0,
                "pri": 3,
                "precondition": "",
                "steps": ["步骤A"],
                "expects": ["期望A"],
                "stepType": ["step"],
                "project": 2,
                "execution": 3,
            },
        )
    ]
    assert result.total == 2
    assert [item.id for item in result.items] == [456, 123]
    assert [item.status for item in result.items] == ["success", "success"]


@pytest.mark.anyio
async def test_list_execution_cases_fetches_case_details_and_normalizes_fields() -> None:
    service = ZentaoTestCaseService(testcase_client=FakeTestCaseClient())

    result = await service.list_execution_cases(11, ImportListQuery())

    assert result.total == 1
    assert result.items[0].id == "123"
    assert result.items[0].module == "Login Module"
    assert result.items[0].title == "第二条测试用例"
    assert result.items[0].preconditions == "User is registered"
    assert result.items[0].steps == "1. Enter account and password\n2. Click login"
    assert result.items[0].expectedResults == "1. Input succeeds\n2. Login succeeds"
    assert result.items[0].priority == "P1"
    assert result.items[0].caseType == "functional"
    assert result.items[0].status == "normal"
    assert result.items[0].lastRunDate == "2026-06-10T09:30:00+08:00"
    assert result.items[0].lastRunResult == "pass"
    assert result.items[0].orderNo == 1
    assert result.items[0].deleted is False


@pytest.mark.anyio
async def test_list_execution_cases_keeps_list_metadata_aligned_after_invalid_id() -> None:
    class ClientWithInvalidListItem(FakeTestCaseClient):
        async def list_execution_testcases(
            self,
            execution_id: int,
            params: dict[str, str | int],
        ) -> dict[str, object]:
            del execution_id, params
            return {
                "status": "success",
                "total": "2",
                "testcases": [
                    {"id": "invalid", "status": "blocked"},
                    {"id": 999, "status": "normal", "lastRunResult": "pass"},
                ],
            }

        async def get_testcase(self, case_id: int) -> dict[str, object]:
            assert case_id == 999
            return {
                "status": "success",
                "testcase": {"id": 999, "title": "有效用例"},
            }

    service = ZentaoTestCaseService(testcase_client=ClientWithInvalidListItem())

    result = await service.list_execution_cases(11, ImportListQuery())

    assert len(result.items) == 1
    assert result.items[0].status == "normal"
    assert result.items[0].lastRunResult == "pass"


@pytest.mark.anyio
async def test_create_testcases_updates_when_same_title_exists_in_execution() -> None:
    testcase_client = FakeTestCaseClient()
    service = ZentaoTestCaseService(testcase_client=testcase_client)

    result = await service.create_testcases(
        BatchCreateCaseRequest(
            productID=1,
            project=2,
            execution=3,
            cases=[
                {
                    "title": "第二条测试用例",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "",
                    "steps": ["步骤A"],
                    "expects": ["期望A"],
                }
            ],
        )
    )

    assert testcase_client.payloads == []
    assert testcase_client.updated_payloads == [
        (
            123,
            {
                "productID": 1,
                "title": "第二条测试用例",
                "module": 0,
                "story": 0,
                "pri": 3,
                "precondition": "",
                "steps": ["步骤A"],
                "expects": ["期望A"],
                "stepType": ["step"],
                "project": 2,
                "execution": 3,
            },
        )
    ]
    assert result.total == 1
    assert result.items[0].id == 123
    assert result.items[0].status == "success"


@pytest.mark.anyio
async def test_create_testcases_updates_duplicate_title_within_same_batch() -> None:
    testcase_client = FakeTestCaseClient()
    service = ZentaoTestCaseService(testcase_client=testcase_client)

    result = await service.create_testcases(
        BatchCreateCaseRequest(
            productID=1,
            project=2,
            execution=0,
            cases=[
                {
                    "title": "批内重复用例",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "",
                    "steps": ["步骤1"],
                    "expects": ["期望1"],
                },
                {
                    "title": "批内重复用例",
                    "module": 0,
                    "story": 0,
                    "pri": 3,
                    "precondition": "",
                    "steps": ["步骤2"],
                    "expects": ["期望2"],
                },
            ],
        )
    )

    assert testcase_client.payloads == [
        {
            "productID": 1,
            "title": "批内重复用例",
            "module": 0,
            "story": 0,
            "pri": 3,
            "precondition": "",
            "steps": ["步骤1"],
            "expects": ["期望1"],
            "stepType": ["step"],
            "project": 2,
            "execution": 0,
        }
    ]
    assert testcase_client.updated_payloads == [
        (
            456,
            {
                "productID": 1,
                "title": "批内重复用例",
                "module": 0,
                "story": 0,
                "pri": 3,
                "precondition": "",
                "steps": ["步骤2"],
                "expects": ["期望2"],
                "stepType": ["step"],
                "project": 2,
                "execution": 0,
            },
        )
    ]
    assert result.total == 2
    assert [item.id for item in result.items] == [456, 456]


@pytest.mark.anyio
async def test_create_testcases_checks_all_existing_case_pages() -> None:
    class PaginatedTestCaseClient(FakeTestCaseClient):
        async def list_execution_testcases(
            self,
            execution_id: int,
            params: dict[str, str | int],
        ) -> dict[str, object]:
            assert execution_id == 3
            page = int(params["pageID"])
            return {
                "status": "success",
                "total": "2",
                "testcases": [{"id": 1000 + page}],
            }

        async def get_testcase(self, case_id: int) -> dict[str, object]:
            return {
                "status": "success",
                "testcase": {
                    "id": case_id,
                    "title": "目标用例" if case_id == 1002 else "其他用例",
                },
            }

    testcase_client = PaginatedTestCaseClient()
    service = ZentaoTestCaseService(testcase_client=testcase_client)

    result = await service.create_testcases(
        BatchCreateCaseRequest(
            productID=1,
            project=2,
            execution=3,
            cases=[{"title": "目标用例", "steps": ["步骤"], "expects": ["预期"]}],
        )
    )

    assert testcase_client.payloads == []
    assert testcase_client.updated_payloads[0][0] == 1002
    assert result.items[0].id == 1002

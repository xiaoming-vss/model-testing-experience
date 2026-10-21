import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.zentao_case_gateway import ZentaoCaseGateway


class Client:
    def __init__(self, repeat=False):
        self.calls = []
        self.repeat = repeat

    async def call(self, name, args, **kwargs):
        self.calls.append((name, args))
        if name == "get_executions_executionID_testcases":
            page = args["pageID"]
            rows = range(1, 101) if page == 1 or self.repeat else [101]
            return {
                "testcases": [{"id": str(i + 1000), "case": str(i)} for i in rows],
                "total": 101,
            }
        if name == "get_testcases_caseID":
            return {"testcase": {"id": args["caseID"], "title": "用例" + str(args["caseID"])}}
        return {"status": "success", "id": 200}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_all_pages_are_read_and_update_requires_explicit_remote_id():
    client = Client()
    gateway = ZentaoCaseGateway(client)
    assert len(await gateway.catalog(201)) == 101
    case = {"title": "新增", "steps": ["步骤"], "expects": ["结果"]}
    target = {"productID": 9, "project": 101, "execution": 201}
    assert await gateway.write(case, target, None) == 200
    assert await gateway.write(case, target, 200) == 200
    writes = [(n, a) for n, a in client.calls if n.startswith(("post", "put"))]
    assert [n for n, _ in writes] == ["post_testcases", "put_testcases_testcasID"]
    assert writes[1][1]["testcasID"] == 200
    assert len([1 for n, _ in client.calls if n == "get_testcases_caseID"]) == 101


@pytest.mark.asyncio
async def test_repeated_pages_abort_before_writes():
    client = Client(repeat=True)
    with pytest.raises(AppError, match="分页重复"):
        await ZentaoCaseGateway(client).catalog(201)
    assert all(n.startswith("get_") for n, _ in client.calls)

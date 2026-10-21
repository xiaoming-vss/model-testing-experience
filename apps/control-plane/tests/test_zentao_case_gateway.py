from unittest.mock import AsyncMock

import pytest

from testing_agent.core.errors import AppError
from testing_agent.services.zentao_case_gateway import ZentaoCaseGateway, content_matches


class Client:
    def __init__(self):
        self.calls = []

    async def call(self, name, args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name == "get_executions_executionID_testcases":
            return {
                "testcases": [
                    {"case": 71, "id": 900, "title": "same"},
                    {"case": 72, "id": 901, "title": "same"},
                ],
                "total": 2,
            }
        if name == "get_testcases_caseID":
            return {"testcase": {"id": args["caseID"], "title": "same", "product": 1, "story": 3}}
        return {"status": "success", "id": args.get("testcasID", 73)}


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", [True, 1.5, "1.5", -1, 2_147_483_648])
async def test_catalog_rejects_invalid_ids_before_list_normalization(identifier):
    client = Client()
    client.call = AsyncMock(
        return_value={"testcases": [{"case": identifier, "title": "case"}], "total": 1}
    )
    with pytest.raises(AppError) as error:
        await ZentaoCaseGateway(client).catalog(2)
    assert error.value.http_code == 502


@pytest.mark.asyncio
async def test_catalog_preserves_duplicate_titles_and_reuses_one_scan():
    client = Client()
    gateway = ZentaoCaseGateway(client)
    assert set(await gateway.catalog(2)) == {71, 72}
    await gateway.catalog(2)
    assert len(client.calls) == 1
    # Titles in list responses remove the previous per-existing-case detail fanout.
    assert client.calls[0][0] == "get_executions_executionID_testcases"


@pytest.mark.asyncio
async def test_write_does_not_infer_update_from_title():
    client = Client()
    gateway = ZentaoCaseGateway(client)
    target = {"productID": 1, "project": 4, "execution": 2, "story": 3}
    payload = {"title": "same", "steps": ["step"], "expects": ["expected"]}
    await gateway.catalog(2)
    assert await gateway.write(payload, target, None) == 73
    assert await gateway.write(payload, target, 72) == 72
    assert [call[0] for call in client.calls[1:]] == ["post_testcases", "put_testcases_testcasID"]
    assert all(call[2]["write"] for call in client.calls[1:])


@pytest.mark.asyncio
async def test_remote_membership_is_checked_before_binding():
    gateway = ZentaoCaseGateway(Client())
    with pytest.raises(AppError, match="不属于目标执行"):
        await gateway.verify_target(99, {"execution": 2, "productID": 1, "story": 3})
    with pytest.raises(AppError, match="不属于目标产品或需求"):
        await gateway.verify_target(71, {"execution": 2, "productID": 1, "story": 999})


def test_reconcile_matches_full_payload_not_title_only():
    payload = {
        "title": "same",
        "precondition": "before",
        "pri": 3,
        "module": 0,
        "story": 3,
        "steps": ["step"],
        "expects": ["expected"],
    }
    detail = {**payload, "steps": [{"desc": "step", "expect": "expected"}]}
    assert content_matches(detail, payload)
    assert not content_matches(
        {**detail, "steps": [{"desc": "changed", "expect": "expected"}]}, payload
    )
    assert not content_matches({**detail, "module": 7}, payload)

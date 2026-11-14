"""Setup for visualization lifecycle tests, independent of collected test modules."""

import asyncio

from support.function_case_library import make_sprint
from support.order_api import make_order
from support.project_api import account, project


def order_fixture(api):
    _, owner = account(api, "visual-owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    order = make_order(api, owner, sprint_id)
    return owner, pid, sprint_id, order["orderId"]


def make_llm(api, headers, pid):
    response = api.post(
        f"/v1/projects/{pid}/integrations/llm/connections",
        headers=headers,
        json={
            "name": "llm",
            "baseUrl": "https://llm.example/v1",
            "apiKey": "fixture-secret",
            "modelId": "model",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["connectionId"]


def query(api, statement):
    async def run():
        async with api.app.state.test_sessions() as session:
            return list((await session.scalars(statement)).all())

    return asyncio.run(run())

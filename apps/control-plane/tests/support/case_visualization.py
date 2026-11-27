"""Setup for visualization lifecycle tests, independent of collected test modules."""

import asyncio

from support.function_case_library import make_sprint
from support.order_api import make_order
from support.project_api import account, project, seed_llm_connection


def order_fixture(api):
    _, owner = account(api, "visual-owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    order = make_order(api, owner, sprint_id)
    return owner, pid, sprint_id, order["orderId"]


def make_llm(api, headers, pid):
    return seed_llm_connection(api, headers, project_id=pid)


def query(api, statement):
    async def run():
        async with api.app.state.test_sessions() as session:
            return list((await session.scalars(statement)).all())

    return asyncio.run(run())

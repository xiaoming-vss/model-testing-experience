"""Shared preparation for local account management tests; no collected cases."""

from __future__ import annotations

import asyncio

from support.project_api import account, api, project  # noqa: F401
from testing_agent.core.security import hash_password
from testing_agent.models.user import User


def super_admin(client, *, must_change_password: bool = False):
    async def create():
        async with client.app.state.test_sessions() as session:
            session.add(
                User(
                    user_id="super-admin",
                    nickname="root",
                    email="root@example.test",
                    password=hash_password("root-password"),
                    is_super_admin=True,
                    super_admin_slot=1,
                    status="active",
                    must_change_password=must_change_password,
                    token_version=0,
                )
            )
            await session.commit()

    asyncio.run(create())
    response = client.post("/v1/login", json={"name": "root", "password": "root-password"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return data, {"Authorization": "Bearer " + data["accessToken"]}

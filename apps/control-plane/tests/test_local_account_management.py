"""Local account security, super administrator and account lifecycle at the HTTP boundary."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_project_membership_api import account, api, project  # noqa: F401

from testing_agent.core.security import hash_password
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.integration_connection import IntegrationConnection
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


def test_registration_requires_email_and_password_policy(api):  # noqa: F811
    missing_email = api.post("/v1/register", json={"name": "a", "password": "test-password"})
    assert missing_email.status_code == 400
    short = api.post(
        "/v1/register", json={"name": "a", "password": "short", "email": "a@example.test"}
    )
    assert short.status_code == 400 and short.json()["code"] == 1007
    long = api.post(
        "/v1/register",
        json={"name": "a", "password": "密" * 25, "email": "a@example.test"},
    )
    assert long.status_code == 400 and long.json()["code"] == 1008
    created = api.post(
        "/v1/register",
        json={"name": "a", "password": "test-password", "email": "A@Example.Test"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["email"] == "a@example.test"
    duplicate = api.post(
        "/v1/register",
        json={"name": "b", "password": "test-password", "email": "a@example.test"},
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == 1002


def test_change_password_revokes_all_sessions(api):  # noqa: F811
    _, first = account(api, "alice")
    second_login = api.post("/v1/login", json={"name": "alice", "password": "test-password"})
    second = {"Authorization": "Bearer " + second_login.json()["data"]["accessToken"]}
    changed = api.put(
        "/v1/user/password",
        headers=first,
        json={"oldPassword": "test-password", "newPassword": "new-password-1"},
    )
    assert changed.status_code == 200, changed.text
    assert api.get("/v1/user", headers=first).status_code == 401
    assert api.get("/v1/user", headers=second).status_code == 401
    assert (
        api.post("/v1/login", json={"name": "alice", "password": "test-password"}).status_code
        == 401
    )
    assert (
        api.post("/v1/login", json={"name": "alice", "password": "new-password-1"}).status_code
        == 200
    )
    wrong_old = api.post("/v1/login", json={"name": "alice", "password": "new-password-1"})
    assert wrong_old.status_code == 200
    token = {"Authorization": "Bearer " + wrong_old.json()["data"]["accessToken"]}
    rejected = api.put(
        "/v1/user/password",
        headers=token,
        json={"oldPassword": "not-the-password", "newPassword": "another-password"},
    )
    assert rejected.status_code == 400 and rejected.json()["code"] == 1010


def test_super_admin_must_change_password_is_enforced_by_backend(api):  # noqa: F811
    login_data, headers = super_admin(api, must_change_password=True)
    assert login_data["mustChangePassword"] is True
    blocked = api.get("/v1/projects", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["code"] == 1003
    assert api.get("/v1/user", headers=headers).status_code == 200
    changed = api.put(
        "/v1/user/password",
        headers=headers,
        json={"oldPassword": "root-password", "newPassword": "root-password-new"},
    )
    assert changed.status_code == 200, changed.text
    assert api.get("/v1/user", headers=headers).status_code == 401
    response = api.post("/v1/login", json={"name": "root", "password": "root-password-new"})
    assert response.status_code == 200
    assert response.json()["data"]["mustChangePassword"] is False
    fresh = {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}
    assert api.get("/v1/projects", headers=fresh).status_code == 200


def test_admin_disable_then_enable_keeps_old_tokens_invalid(api):  # noqa: F811
    _, admin = super_admin(api)
    user, user_headers = account(api, "worker")
    listing = api.get("/v1/admin/users?search=worker&status=active&pageSize=1", headers=admin)
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["items"][0]["userId"] == user["userId"]
    disabled = api.post(
        f"/v1/admin/users/{user['userId']}/disable",
        headers=admin,
        json={"reason": "left the company"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"
    assert api.get("/v1/user", headers=user_headers).status_code == 401
    login = api.post("/v1/login", json={"name": "worker", "password": "test-password"})
    assert login.status_code == 403 and login.json()["code"] == 1004
    enabled = api.post(f"/v1/admin/users/{user['userId']}/enable", headers=admin)
    assert enabled.status_code == 200, enabled.text
    assert api.get("/v1/user", headers=user_headers).status_code == 401
    login = api.post("/v1/login", json={"name": "worker", "password": "test-password"})
    assert login.status_code == 200


def test_admin_reset_password_and_revoke_sessions(api):  # noqa: F811
    _, admin = super_admin(api)
    user, user_headers = account(api, "worker")
    reset = api.post(
        f"/v1/admin/users/{user['userId']}/reset-password",
        headers=admin,
        json={"newPassword": "reset-password"},
    )
    assert reset.status_code == 200, reset.text
    assert api.get("/v1/user", headers=user_headers).status_code == 401
    assert (
        api.post("/v1/login", json={"name": "worker", "password": "test-password"}).status_code
        == 401
    )
    login = api.post("/v1/login", json={"name": "worker", "password": "reset-password"})
    assert login.status_code == 200
    fresh = {"Authorization": "Bearer " + login.json()["data"]["accessToken"]}
    revoked = api.post(f"/v1/admin/users/{user['userId']}/revoke-sessions", headers=admin)
    assert revoked.status_code == 200
    assert api.get("/v1/user", headers=fresh).status_code == 401


def test_admin_delete_transfers_projects_and_cleans_personal_data(api):  # noqa: F811
    _, admin = super_admin(api)
    admin_project = api.post("/v1/projects", headers=admin, json={"name": "shared"})
    assert admin_project.status_code == 200, admin_project.text
    user, user_headers = account(api, "departing")
    user_project = project(api, user_headers, name="shared")

    async def seed_personal_data():
        async with api.app.state.test_sessions() as session:
            session.add(
                ApiEnvironment(
                    environment_id="env-1",
                    project_id=user_project,
                    name="env",
                    base_url="https://api.example.test",
                )
            )
            session.add(
                ApiEnvironmentVar(
                    env_var_id="var-1",
                    environment_id="env-1",
                    var_key="token",
                    value="secret",
                    is_secret=True,
                    secret_user_id=user["userId"],
                )
            )
            session.add(
                IntegrationConnection(
                    connection_id="personal",
                    user_id=user["userId"],
                    provider="llm",
                    name="personal",
                    project_id=user_project,
                    secret_json={"apiKey": "secret"},
                )
            )
            await session.commit()

    asyncio.run(seed_personal_data())
    deleted = api.delete(f"/v1/admin/users/{user['userId']}", headers=admin)
    assert deleted.status_code == 200, deleted.text
    assert api.get("/v1/user", headers=user_headers).status_code == 401

    async def remaining():
        async with api.app.state.test_sessions() as session:
            return (
                await session.scalar(
                    select(ApiEnvironmentVar).where(ApiEnvironmentVar.env_var_id == "var-1")
                ),
                await session.scalar(
                    select(IntegrationConnection).where(
                        IntegrationConnection.connection_id == "personal"
                    )
                ),
            )

    variable, connection = asyncio.run(remaining())
    assert variable is None and connection is None
    projects = api.get("/v1/projects", headers=admin).json()["data"]["items"]
    transferred = next(item for item in projects if item["projectId"] == user_project)
    assert transferred["userId"] == "super-admin"
    assert transferred["name"] == "shared-departing"
    assert transferred["isSuperAdmin"] is True


def test_super_admin_sees_all_projects_but_normal_user_cannot_use_admin_api(api):  # noqa: F811
    _, normal = account(api, "normal")
    pid = project(api, normal, name="normal-project")
    _, admin = super_admin(api)
    assert api.get("/v1/user", headers=admin).json()["data"]["isSuperAdmin"] is True
    added = api.post(
        f"/v1/projects/{pid}/members",
        headers=normal,
        json={"name": "root", "role": "viewer"},
    )
    assert added.status_code == 200, added.text
    projects = api.get("/v1/projects", headers=admin).json()["data"]["items"]
    assert [item["projectId"] for item in projects] == [pid]
    assert projects[0]["role"] == "owner"
    assert projects[0]["isSuperAdmin"] is True
    forbidden = api.get("/v1/admin/users", headers=normal)
    assert forbidden.status_code == 403


def test_login_lockout_after_repeated_failures(api):  # noqa: F811
    account(api, "locked")
    for _ in range(4):
        response = api.post("/v1/login", json={"name": "locked", "password": "wrong-password"})
        assert response.status_code == 401
    fifth = api.post("/v1/login", json={"name": "locked", "password": "wrong-password"})
    assert fifth.status_code == 423 and fifth.json()["code"] == 1005
    still_locked = api.post("/v1/login", json={"name": "locked", "password": "test-password"})
    assert still_locked.status_code == 423

    async def expire_lock():
        from testing_agent.models.login_rate_limit import LoginRateLimit

        async with api.app.state.test_sessions() as session:
            user = await session.scalar(select(User).where(User.nickname == "locked"))
            user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
            limiter = await session.scalar(
                select(LoginRateLimit).where(LoginRateLimit.username == "locked")
            )
            if limiter is not None:
                limiter.blocked_until = datetime.now(UTC) - timedelta(seconds=1)
                limiter.window_started_at = datetime.now(UTC) - timedelta(minutes=20)
            await session.commit()

    asyncio.run(expire_lock())
    assert (
        api.post("/v1/login", json={"name": "locked", "password": "test-password"}).status_code
        == 200
    )


def test_admin_can_backfill_email(api):  # noqa: F811
    _, admin = super_admin(api)
    user, _ = account(api, "legacy")
    updated = api.put(
        f"/v1/admin/users/{user['userId']}/email",
        headers=admin,
        json={"email": " Filled@Example.Test "},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["email"] == "filled@example.test"

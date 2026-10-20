import asyncio
from dataclasses import replace

from sqlalchemy import select
from support.ldap_cutover import ldap_settings
from support.local_account_management import super_admin
from support.project_api import account, api, project  # noqa: F401

from testing_agent.core.config import Settings
from testing_agent.domain.ldap_identity import DirectoryIdentity
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.ldap_accounts import LdapAccountService


def test_cutover_link_and_explicit_local_recovery_preserve_resources_and_revoke_tokens(api):  # noqa: F811
    _, admin_headers = super_admin(api)
    owner, old_owner_token = account(api, "owner")
    member, old_member_token = account(api, "member")
    project_id = project(api, old_owner_token)
    response = api.post(
        f"/v1/projects/{project_id}/members",
        headers=old_owner_token,
        json={"name": "member", "role": "viewer"},
    )
    assert response.status_code == 200
    settings = ldap_settings()
    settings = replace(settings, ldap=replace(settings.ldap, auto_link_by_username=True))

    async def enable_and_link():
        async with api.app.state.test_sessions() as session:
            await AuthModeService(AuthRuntimeRepository(session), settings).switch()
            users = UserRepository(session)
            identity = DirectoryIdentity(
                "550e8400-e29b-41d4-a716-446655440009",
                "owner",
                "uid=owner,dc=test",
                ("owner@example.test",),
                True,
                True,
            )
            service = LdapAccountService(users, auto_link=True)
            snapshot = await service.snapshot(identity)
            await users.rollback()
            linked = await service.persist(identity, snapshot)
            assert linked.user_id == owner["userId"]
            owned = await session.scalar(select(Project).where(Project.project_id == project_id))
            assert owned.user_id == owner["userId"]
            membership = await session.scalar(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == member["userId"],
                )
            )
            assert membership.role == "viewer"

    asyncio.run(enable_and_link())
    assert api.get("/v1/user", headers=old_owner_token).status_code == 401
    assert api.get("/v1/user", headers=old_member_token).status_code == 401
    assert api.get("/v1/user", headers=admin_headers).status_code == 200

    async def turn_off():
        async with api.app.state.test_sessions() as session:
            await AuthModeService(
                AuthRuntimeRepository(session), Settings.from_mapping({})
            ).switch()
            assert (
                await UserRepository(session).get_by_user_id(member["userId"])
            ).status == "pending_ldap"

    asyncio.run(turn_off())
    response = api.post(f"/v1/admin/users/{member['userId']}/enable", headers=admin_headers)
    assert response.status_code == 200 and response.json()["data"]["status"] == "active"
    assert api.get("/v1/user", headers=old_member_token).status_code == 401
    assert (
        api.post("/v1/login", json={"name": "member", "password": "test-password"}).status_code
        == 200
    )
    assert (
        api.post("/v1/login", json={"name": "owner", "password": "test-password"}).status_code
        == 403
    )

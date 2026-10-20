from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.core.ldap_config import LdapSettings
from testing_agent.models.auth_runtime import AuthRuntime
from testing_agent.models.user import User
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(AuthRuntime.__table__.create)
        await conn.run_sync(User.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(AuthRuntime(id=1))
        session.add_all(
            [
                User(
                    user_id="admin",
                    nickname="root",
                    password="hash",
                    is_super_admin=True,
                    status="active",
                    auth_source="local",
                    token_version=3,
                ),
                User(
                    user_id="local",
                    nickname="local",
                    password="hash",
                    status="active",
                    token_version=2,
                ),
                User(
                    user_id="disabled",
                    nickname="disabled",
                    password="hash",
                    status="disabled",
                    disabled_reason="manual",
                    disabled_by="admin",
                    token_version=7,
                ),
                User(
                    user_id="ldap",
                    nickname="ldap",
                    password="",
                    status="active",
                    auth_source="ldap",
                    external_id="550e8400-e29b-41d4-a716-446655440000",
                    token_version=1,
                ),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


def ldap_settings():
    return replace(
        Settings.from_mapping({}),
        ldap=LdapSettings(
            enabled=True,
            server_url="ldap://directory.test",
            bind_dn="uid=reader,dc=test",
            bind_password="test",
            user_search_base="dc=test",
            access_group_dn="cn=platform,dc=test",
        ),
    )


async def test_cutover_preserves_admin_disabled_records_and_retries(session):
    runtime = AuthRuntimeRepository(session)
    service = AuthModeService(runtime, ldap_settings())
    with pytest.raises(AppError):
        await service.require_current()
    assert await service.switch()
    users = UserRepository(session)
    local = await users.get_by_user_id("local")
    assert local.status == "pending_ldap" and local.token_version == 3 and local.password == "hash"
    disabled = await users.get_by_user_id("disabled")
    assert disabled.status == "disabled" and disabled.disabled_reason == "manual"
    assert disabled.disabled_by == "admin" and disabled.token_version == 8
    admin = await users.get_by_user_id("admin")
    assert admin.status == "active" and admin.token_version == 3
    ldap = await users.get_by_user_id("ldap")
    assert ldap.status == "active" and ldap.token_version == 2
    assert await service.require_current() == 1
    assert not await service.switch()
    assert (await users.get_by_user_id("ldap")).token_version == 2


async def test_disable_does_not_restore_pending_or_local_password(session):
    runtime = AuthRuntimeRepository(session)
    await AuthModeService(runtime, ldap_settings()).switch()
    local = AuthModeService(runtime, Settings.from_mapping({}))
    assert await local.switch()
    assert await local.require_current() == 2
    users = UserRepository(session)
    assert (await users.get_by_user_id("local")).status == "pending_ldap"
    assert (await users.get_by_user_id("ldap")).password == ""
    assert (await users.get_by_user_id("ldap")).auth_source == "ldap"


async def test_config_change_fences_old_instance_without_repeated_revocation(session):
    runtime = AuthRuntimeRepository(session)
    old = ldap_settings()
    await AuthModeService(runtime, old).switch()
    new = replace(old, ldap=replace(old.ldap, auto_link_by_username=True))
    service = AuthModeService(runtime, new)
    with pytest.raises(AppError):
        await service.require_current()
    await service.switch()
    assert await service.require_current() == 2
    with pytest.raises(AppError):
        await AuthModeService(runtime, old).require_current()
    assert (await UserRepository(session).get_by_user_id("ldap")).token_version == 2


async def test_missing_usable_admin_aborts_all_changes(session):
    users = UserRepository(session)
    admin = await users.get_by_user_id("admin")
    admin.must_change_password = True
    await session.commit()
    with pytest.raises(AppError):
        await AuthModeService(AuthRuntimeRepository(session), ldap_settings()).switch()
    assert (await users.get_by_user_id("local")).status == "active"
    assert (await AuthRuntimeRepository(session).get()).generation == 0


async def test_stale_local_instance_cannot_enable_pending_user(session):
    from testing_agent.repositories.project import ProjectRepository
    from testing_agent.services.user_admin import UserAdminService

    runtime = AuthRuntimeRepository(session)
    await AuthModeService(runtime, ldap_settings()).switch()
    settings = Settings.from_mapping({})
    admin = UserAdminService(
        UserRepository(session),
        ProjectRepository(session),
        settings,
        mode=AuthModeService(runtime, settings),
    )
    with pytest.raises(AppError) as error:
        await admin.enable("admin", "local")
    assert error.value.code == 1026
    assert (await UserRepository(session).get_by_user_id("local")).status == "pending_ldap"

from unittest.mock import AsyncMock

import jwt
import pytest
from test_ldap_cutover import ldap_settings, session  # noqa: F401

from testing_agent.core.errors import AppError
from testing_agent.domain.ldap_identity import (
    DirectoryCredentialsRejected,
    DirectoryIdentity,
    DirectoryUnavailable,
)
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.auth import LoginRequest
from testing_agent.services.auth import AuthService
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.ldap_login import LdapLoginService

IDENTITY = DirectoryIdentity(
    "550e8400-e29b-41d4-a716-446655440001",
    "new-user",
    "uid=new-user,dc=test",
    ("new-user@example.test",),
    True,
    True,
)


async def service(session):  # noqa: F811
    connection = await session.connection()
    await connection.run_sync(LoginRateLimit.__table__.create)
    await session.commit()
    settings = ldap_settings()
    mode = AuthModeService(AuthRuntimeRepository(session), settings)
    await mode.switch()
    directory = AsyncMock()
    directory.lookup.return_value = IDENTITY
    users = UserRepository(session)
    limits = LoginRateLimitRepository(session)
    return LdapLoginService(users, limits, mode, settings, directory), directory


async def test_complete_jit_login_issues_twelve_hour_token(session):  # noqa: F811
    login, directory = await service(session)
    result = await login.login(
        LoginRequest(name="new-user", password="x" * 100, auth_method="ldap"), "ip"
    )
    claims = jwt.decode(result["accessToken"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 12 * 3600
    assert (await login.users.get_by_name("new-user")).auth_source == "ldap"
    directory.verify_password.assert_awaited_once()


async def test_directory_outage_does_not_add_failure_or_user(session):  # noqa: F811
    login, directory = await service(session)
    directory.lookup.side_effect = DirectoryUnavailable()
    with pytest.raises(AppError) as error:
        await login.login(LoginRequest(name="new-user", password="password"), "ip")
    assert error.value.http_code == 503
    assert await login.limits.get("new-user", "ip", "ldap") is None
    assert await login.users.get_by_name("new-user") is None


async def test_wrong_password_limits_unknown_user_without_creating_account(session):  # noqa: F811
    login, directory = await service(session)
    directory.verify_password.side_effect = DirectoryCredentialsRejected()
    for _ in range(5):
        with pytest.raises(AppError) as error:
            await login.login(LoginRequest(name="new-user", password="wrong"), "ip")
        assert error.value.http_code == 401
    with pytest.raises(AppError) as error:
        await login.login(LoginRequest(name="new-user", password="wrong"), "ip")
    assert error.value.http_code == 429
    assert await login.users.get_by_name("new-user") is None
    assert await login.limits.get("new-user", "ip", "local") is None


async def test_switch_during_bind_rejects_commit(session):  # noqa: F811
    login, directory = await service(session)

    async def change_mode(*args):
        row = await AuthRuntimeRepository(session).get(for_update=True)
        row.generation += 1
        await session.commit()

    directory.verify_password.side_effect = change_mode
    with pytest.raises(AppError) as error:
        await login.login(LoginRequest(name="new-user", password="right"), "ip")
    assert error.value.http_code == 503
    assert await login.users.get_by_name("new-user") is None


async def test_dispatch_does_not_fall_back_to_local_password(session):  # noqa: F811
    login, directory = await service(session)
    auth = AuthService(login.users, login.limits, login.settings, ldap_login=login)
    directory.lookup.side_effect = DirectoryUnavailable()
    with pytest.raises(AppError) as error:
        await auth.login(
            LoginRequest.model_validate({"name": "root", "password": "hash", "authMethod": "ldap"})
        )
    assert error.value.http_code == 503
    assert (await login.users.get_by_user_id("admin")).failed_login_count == 0


async def test_empty_password_rejected_without_directory_call(session):  # noqa: F811
    login, directory = await service(session)
    with pytest.raises(AppError) as error:
        await login.login(LoginRequest(name="new-user", password=""), "ip")
    assert error.value.http_code == 400
    directory.lookup.assert_not_awaited()


async def test_stale_local_instance_cannot_register_or_login_ordinary_user(session):  # noqa: F811
    from testing_agent.core.config import Settings
    from testing_agent.schemas.auth import RegisterRequest

    login, _ = await service(session)
    settings = Settings.from_mapping({})
    auth = AuthService(
        login.users,
        login.limits,
        settings,
        mode=AuthModeService(AuthRuntimeRepository(session), settings),
    )
    with pytest.raises(AppError) as error:
        await auth.register(
            RegisterRequest(name="bypass", email="bypass@test", password="long-password")
        )
    assert error.value.code == 1026
    await session.rollback()
    with pytest.raises(AppError) as error:
        await auth.login(LoginRequest(name="local", password="hash"))
    assert error.value.code == 1026
    assert await login.users.get_by_name("bypass") is None


async def test_admin_local_entry_does_not_depend_on_matching_runtime_mode(session):  # noqa: F811
    from testing_agent.core.config import Settings

    login, directory = await service(session)
    settings = Settings.from_mapping({})
    auth = AuthService(
        login.users,
        login.limits,
        settings,
        mode=AuthModeService(AuthRuntimeRepository(session), settings),
    )
    # Fixture intentionally has an unusable password hash; it must reach local validation,
    # not return directory failure or mode mismatch.
    with pytest.raises(AppError) as error:
        await auth.login(LoginRequest(name="root", password="wrong"))
    assert error.value.http_code == 401
    directory.lookup.assert_not_awaited()


async def test_http_login_dispatches_explicit_ldap_and_keeps_legacy_local_default(session):  # noqa: F811
    import httpx

    from testing_agent.api.deps import get_auth_service
    from testing_agent.app import create_app

    login, directory = await service(session)
    auth = AuthService(login.users, login.limits, login.settings, ldap_login=login, mode=login.mode)
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: auth
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/login",
            json={
                "name": "new-user",
                "password": "directory-password",
                "authMethod": "ldap",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["accessToken"]
        directory.lookup.reset_mock()
        response = await client.post(
            "/v1/login",
            json={
                "name": "new-user",
                "password": "directory-password",
            },
        )
        assert response.status_code == 403
        directory.lookup.assert_not_awaited()


async def test_success_clears_ldap_failure_limit(session):  # noqa: F811
    login, directory = await service(session)
    directory.verify_password.side_effect = DirectoryCredentialsRejected()
    with pytest.raises(AppError):
        await login.login(LoginRequest(name="new-user", password="wrong"), "ip")
    assert (await login.limits.get("new-user", "ip", "ldap")).attempt_count == 1
    await session.rollback()
    directory.verify_password.side_effect = None
    await login.login(LoginRequest(name="new-user", password="correct"), "ip")
    assert await login.limits.get("new-user", "ip", "ldap") is None


async def test_linked_user_reaches_account_lock_threshold(session):  # noqa: F811
    from dataclasses import replace

    login, directory = await service(session)
    existing = replace(
        IDENTITY, external_id="550e8400-e29b-41d4-a716-446655440000", username="ldap"
    )
    directory.lookup.return_value = existing
    directory.verify_password.side_effect = DirectoryCredentialsRejected()
    for index in range(5):
        with pytest.raises(AppError) as error:
            await login.login(LoginRequest(name="ldap", password="wrong"), f"ip-{index}")
        assert error.value.http_code == (423 if index == 4 else 401)
    user = await login.users.get_by_user_id("ldap")
    assert user.failed_login_count == 5 and user.locked_until is not None

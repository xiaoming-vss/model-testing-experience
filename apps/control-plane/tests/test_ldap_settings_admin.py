from dataclasses import asdict, replace
from unittest.mock import AsyncMock, patch

import pytest
from test_ldap_cutover import ldap_settings, session  # noqa: F401

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.ldap_settings import LdapSettingsService, effective_settings


def bootstrap():
    return replace(Settings.from_mapping({}), integration_key="secure-test-encryption-key-for-ldap")


def config():
    return {
        **asdict(ldap_settings().ldap),
        "directory_rules_verified": True,
        "active_user_filter": "(testState=active)",
        "disabled_user_filter": "(testState=disabled)",
    }


async def test_save_encrypts_secret_and_switches_atomically(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    view = await service.read("admin")
    assert view["source"] == "database"
    response = await service.save("admin", view["generation"], config())
    assert response["config"]["enabled"] and response["passwordConfigured"]
    assert "bind_password" not in response["config"]
    row = await runtime.get()
    assert row.ldap_config["bind_password_encrypted"].startswith("enc:v1:")
    assert "bind_password" not in row.ldap_config
    effective = await effective_settings(runtime, bootstrap())
    assert effective.ldap.bind_password == "test"
    assert await AuthModeService(runtime, effective).require_current() == response["generation"]
    user = await UserRepository(session).get_by_user_id("local")
    assert user.status == "pending_ldap" and user.token_version == 3


async def test_omitted_password_preserved_and_disabled_draft_not_ignored(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    first = await service.save("admin", 0, {**config(), "enabled": False})
    second = await service.save("admin", first["generation"], {"server_url": "ldap://changed.test"})
    assert second["generation"] > first["generation"]
    effective = await effective_settings(runtime, bootstrap())
    assert (
        effective.ldap.bind_password == "test"
        and effective.ldap.server_url == "ldap://changed.test"
    )
    cleared = await service.save("admin", second["generation"], {}, clear_password=True)
    assert not cleared["passwordConfigured"]


async def test_version_conflict_and_ordinary_user_rejected(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    with pytest.raises(AppError) as error:
        await service.read("local")
    assert error.value.http_code == 403
    await service.save("admin", 0, {**config(), "enabled": False})
    with pytest.raises(AppError) as error:
        await service.save("admin", 0, config())
    assert error.value.http_code == 409


async def test_invalid_configuration_never_changes_mode_or_accounts(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    with pytest.raises(AppError):
        await service.save("admin", 0, {**config(), "access_group_dn": ""})
    row = await runtime.get()
    assert row.generation == 0 and row.ldap_config is None and row.mode == "local"
    assert (await UserRepository(session).get_by_user_id("local")).status == "active"


async def test_test_endpoint_does_not_save_or_switch(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    with patch("testing_agent.services.ldap_settings.LdapDirectory") as directory:
        directory.return_value.check_connection = AsyncMock()
        result = await service.test("admin", config())
    assert result["connected"]
    row = await runtime.get()
    assert row.ldap_config is None and row.generation == 0


async def test_disable_via_page_preserves_ldap_identity_and_pending(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    service = LdapSettingsService(runtime, bootstrap())
    first = await service.save("admin", 0, config())
    await service.save("admin", first["generation"], {"enabled": False})
    assert (await UserRepository(session).get_by_user_id("local")).status == "pending_ldap"
    assert (await UserRepository(session).get_by_user_id("ldap")).auth_source == "ldap"


async def test_unconfigured_database_never_uses_file_values(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    legacy = replace(bootstrap(), ldap=ldap_settings().ldap)
    service = LdapSettingsService(runtime, legacy)
    view = await service.read("admin")
    assert view["source"] == "database"
    assert not view["config"]["enabled"] and not view["passwordConfigured"]
    assert view["config"]["server_url"] == ""
    assert not (await effective_settings(runtime, legacy)).ldap.enabled
    await service.save("admin", 0, {"server_url": "ldap://draft.test"})
    assert (await effective_settings(runtime, legacy)).ldap.bind_password == ""


async def test_missing_ldap_config_in_ldap_mode_fails_closed(session):  # noqa: F811
    runtime = AuthRuntimeRepository(session)
    row = await runtime.get()
    row.mode = "ldap"
    await runtime.commit()
    with pytest.raises(AppError):
        await effective_settings(runtime, bootstrap())

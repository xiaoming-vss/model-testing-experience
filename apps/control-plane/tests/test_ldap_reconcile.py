from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from support.ldap_cutover import ldap_settings, session  # noqa: F401

from testing_agent.domain.ldap_identity import DirectoryIdentity, DirectoryUnavailable
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.ldap_reconcile import LdapReconciler

ID = "550e8400-e29b-41d4-a716-446655440000"
IDENTITY = DirectoryIdentity(ID, "renamed", "uid=renamed,dc=test", (), True, True)


async def setup(session):  # noqa: F811
    settings = ldap_settings()
    await AuthModeService(AuthRuntimeRepository(session), settings).switch()
    directory = AsyncMock()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    return LdapReconciler(factory, settings, directory), directory


async def current(session, identifier="ldap"):  # noqa: F811
    await session.rollback()
    return await UserRepository(session).get_by_user_id(identifier)


@pytest.mark.parametrize(
    "identity", [None, replace(IDENTITY, enabled=False), replace(IDENTITY, direct_member=False)]
)
async def test_confirmed_loss_disables_once_and_preserves_other_accounts(session, identity):  # noqa: F811
    reconciler, directory = await setup(session)
    directory.inspect.return_value = {ID: identity}
    assert await reconciler.run_once() == 1
    user = await current(session)
    assert user.status == "disabled" and user.token_version == 3
    assert user.disabled_reason == "LDAP 对账禁用" and user.disabled_by == ""
    assert user.disabled_at is not None
    timestamp = user.disabled_at
    await session.rollback()
    assert await reconciler.run_once() == 0
    user = await current(session)
    assert user.token_version == 3 and user.disabled_at == timestamp
    assert (await current(session, "disabled")).disabled_reason == "manual"
    assert (await current(session, "local")).status == "pending_ldap"
    assert (await current(session, "admin")).status == "active"


async def test_directory_failure_makes_no_state_changes(session):  # noqa: F811
    reconciler, directory = await setup(session)
    directory.inspect.side_effect = DirectoryUnavailable("partial")
    with pytest.raises(DirectoryUnavailable):
        await reconciler.run_once()
    assert (await current(session)).status == "active"


async def test_incomplete_result_is_not_deletion(session):  # noqa: F811
    reconciler, directory = await setup(session)
    directory.inspect.return_value = {}
    with pytest.raises(DirectoryUnavailable):
        await reconciler.run_once()
    assert (await current(session)).status == "active"


async def test_existing_lease_skips_directory_query(session):  # noqa: F811
    reconciler, directory = await setup(session)
    row = await AuthRuntimeRepository(session).get(for_update=True)
    row.reconcile_owner = "other"
    row.reconcile_until = datetime.now(UTC) + timedelta(seconds=60)
    await session.commit()
    assert await reconciler.run_once() is None
    directory.inspect.assert_not_awaited()


async def test_configuration_change_during_query_discards_round(session):  # noqa: F811
    reconciler, directory = await setup(session)

    async def change(_):
        row = await AuthRuntimeRepository(session).get(for_update=True)
        row.generation += 1
        await session.commit()
        return {ID: None}

    directory.inspect.side_effect = change
    with pytest.raises(DirectoryUnavailable):
        await reconciler.run_once()
    assert (await current(session)).status == "active"


async def test_directory_recovery_never_reenables_local_account(session):  # noqa: F811
    reconciler, directory = await setup(session)
    user = await current(session)
    user.status = "disabled"
    user.disabled_reason = "manual"
    await session.commit()
    directory.inspect.return_value = {ID: IDENTITY}
    assert await reconciler.run_once() == 0
    user = await current(session)
    assert user.status == "disabled" and user.disabled_reason == "manual"


async def test_manual_disable_during_query_preserves_admin_record(session):  # noqa: F811
    reconciler, directory = await setup(session)

    async def disable(_):
        user = await UserRepository(session).get_by_user_id_for_update("ldap")
        user.status = "disabled"
        user.disabled_reason = "administrator decision"
        user.disabled_by = "admin"
        user.token_version += 1
        await session.commit()
        return {ID: None}

    directory.inspect.side_effect = disable
    assert await reconciler.run_once() == 0
    user = await current(session)
    assert user.disabled_reason == "administrator decision" and user.disabled_by == "admin"
    assert user.token_version == 3


async def test_expired_lease_during_query_cannot_apply_results(session):  # noqa: F811
    reconciler, directory = await setup(session)

    async def expire(_):
        row = await AuthRuntimeRepository(session).get(for_update=True)
        row.reconcile_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        return {ID: None}

    directory.inspect.side_effect = expire
    with pytest.raises(DirectoryUnavailable):
        await reconciler.run_once()
    assert (await current(session)).status == "active"


async def test_reconcile_uses_stable_id_and_never_syncs_profile(session):  # noqa: F811
    reconciler, directory = await setup(session)
    directory.inspect.return_value = {ID: IDENTITY}
    assert await reconciler.run_once() == 0
    directory.inspect.assert_awaited_once_with((ID,))
    user = await current(session)
    assert user.nickname == "ldap" and user.email is None

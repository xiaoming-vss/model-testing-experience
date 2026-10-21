from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.errors import AppError
from testing_agent.domain.ldap_identity import DirectoryIdentity
from testing_agent.models.user import User
from testing_agent.repositories.user import UserRepository
from testing_agent.services.ldap_accounts import LdapAccountService

IDENTITY = DirectoryIdentity(
    "550e8400-e29b-41d4-a716-446655440000",
    "alice",
    "uid=alice,dc=test",
    ("alice@example.test",),
    True,
    True,
)


@pytest.fixture
async def users():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield UserRepository(session)
    await engine.dispose()


async def local(users, **changes):
    values = dict(
        user_id="original",
        nickname="alice",
        email="old@example.test",
        password="old-hash",
        status="pending_ldap",
        auth_source="local",
        token_version=4,
    )
    values.update(changes)
    row = User(**values)
    users.add(row)
    await users.commit()
    return row


async def test_pending_link_retains_identity_and_atomically_clears_password(users):
    await local(users)
    service = LdapAccountService(users, auto_link=True)
    snapshot = await service.snapshot(IDENTITY)
    await users.rollback()  # No transaction remains open during directory bind.
    user = await service.persist(IDENTITY, snapshot)
    assert user.user_id == "original"
    assert user.auth_source == "ldap" and user.external_id == IDENTITY.external_id
    assert user.status == "active" and user.password == ""
    assert user.email == "alice@example.test" and user.token_version == 5


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"status": "disabled"}, 1004),
        ({"status": "active"}, 1026),
        ({"is_super_admin": True}, 1021),
        ({"locked_until": timedelta(minutes=10)}, 1005),
    ],
)
async def test_forbidden_candidates_never_link(users, overrides, code):
    overrides = dict(overrides)
    if isinstance(overrides.get("locked_until"), timedelta):
        # Full-suite collection can precede this test by more than the lock window.
        overrides["locked_until"] = datetime.now(UTC) + overrides["locked_until"]
    await local(users, **overrides)
    with pytest.raises(AppError) as error:
        await LdapAccountService(users, auto_link=True).snapshot(IDENTITY)
    assert error.value.code == code


async def test_disabled_auto_link_rejects_same_name(users):
    await local(users)
    with pytest.raises(AppError) as error:
        await LdapAccountService(users, auto_link=False).snapshot(IDENTITY)
    assert error.value.code == 1021


async def test_jit_and_rename_keep_stable_identity_and_token_version(users):
    service = LdapAccountService(users, auto_link=False)
    created = await service.persist(IDENTITY, None)
    identifier = created.user_id
    renamed = replace(IDENTITY, username="alice-new", emails=())
    snapshot = await service.snapshot(renamed)
    await users.rollback()
    user = await service.persist(renamed, snapshot)
    assert user.user_id == identifier and user.nickname == "alice-new"
    assert user.email == "alice@example.test" and user.token_version == 0
    assert len((await users.session.scalars(select(User))).all()) == 1


async def test_conflicting_email_rolls_back_entire_link(users):
    await local(users)
    await local(users, user_id="other", nickname="other", email="alice@example.test")
    service = LdapAccountService(users, auto_link=True)
    snapshot = await service.snapshot(IDENTITY)
    await users.rollback()
    with pytest.raises(AppError) as error:
        await service.persist(IDENTITY, snapshot)
    assert error.value.code == 1021
    original = await users.get_by_user_id("original")
    assert original.status == "pending_ldap" and original.password == "old-hash"
    assert original.external_id is None and original.token_version == 4


async def test_inflight_revocation_cannot_be_overwritten(users):
    original = await local(users)
    service = LdapAccountService(users, auto_link=True)
    snapshot = await service.snapshot(IDENTITY)
    original.token_version += 1
    await users.commit()
    with pytest.raises(AppError) as error:
        await service.persist(IDENTITY, snapshot)
    assert error.value.code == 401
    current = await users.get_by_user_id("original")
    assert current.auth_source == "local" and current.token_version == 5


async def test_inflight_deletion_does_not_create_replacement(users):
    original = await local(users)
    service = LdapAccountService(users, auto_link=True)
    snapshot = await service.snapshot(IDENTITY)
    await users.delete(original)
    await users.commit()
    with pytest.raises(AppError) as error:
        await service.persist(IDENTITY, snapshot)
    assert error.value.code == 401
    assert await users.get_by_name("alice") is None


async def test_new_directory_identity_cannot_take_over_existing_ldap_username(users):
    service = LdapAccountService(users, auto_link=True)
    await service.persist(IDENTITY, None)
    other = replace(IDENTITY, external_id="550e8400-e29b-41d4-a716-446655440001")
    with pytest.raises(AppError) as error:
        await service.snapshot(other)
    assert error.value.code == 1021


@pytest.mark.parametrize("emails,code", [((), 1027), (("a@test", "b@test"), 1021)])
async def test_invalid_jit_email_does_not_create_account(users, emails, code):
    with pytest.raises(AppError) as error:
        await LdapAccountService(users, auto_link=True).persist(
            replace(IDENTITY, emails=emails), None
        )
    assert error.value.code == code
    assert await users.get_by_name("alice") is None


async def test_profile_and_admin_identity_mutations_are_readonly(users):
    from testing_agent.repositories.project import ProjectRepository
    from testing_agent.schemas.auth import ChangePasswordRequest, UpdateProfileRequest
    from testing_agent.services.auth import AuthService
    from testing_agent.services.user_admin import UserAdminService

    user = await LdapAccountService(users, auto_link=False).persist(IDENTITY, None)
    await local(
        users,
        user_id="admin",
        nickname="root",
        email="root@test",
        is_super_admin=True,
        status="active",
    )
    auth = AuthService(users)
    admin = UserAdminService(users, ProjectRepository(users.session))
    calls = [
        lambda: auth.update_profile(user.user_id, UpdateProfileRequest(email="changed@test")),
        lambda: auth.change_password(
            user.user_id, ChangePasswordRequest(old_password="any", new_password="new-password")
        ),
        lambda: admin.update_email("admin", user.user_id, "changed@test"),
        lambda: admin.reset_password("admin", user.user_id, "new-password"),
    ]
    for call in calls:
        with pytest.raises(AppError) as error:
            await call()
        assert error.value.code == 1022
    assert (await auth.get_profile(user.user_id))["authSource"] == "ldap"


async def test_admin_enable_respects_pending_state_and_keeps_valid_lock(users):
    from dataclasses import replace

    from testing_agent.core.config import Settings
    from testing_agent.core.ldap_config import LdapSettings
    from testing_agent.repositories.project import ProjectRepository
    from testing_agent.services.user_admin import UserAdminService

    target = await local(
        users, status="disabled", locked_until=datetime.now(UTC) + timedelta(minutes=10)
    )
    await local(
        users,
        user_id="admin",
        nickname="root",
        email="root@test",
        is_super_admin=True,
        status="active",
    )
    settings = replace(
        Settings.from_mapping({}),
        ldap=LdapSettings(
            enabled=True,
            server_url="ldap://directory.test",
            bind_dn="uid=reader,dc=test",
            bind_password="test",
            user_search_base="dc=test",
            access_group_dn="cn=group,dc=test",
        ),
    )
    service = UserAdminService(users, ProjectRepository(users.session), settings)
    result = await service.enable("admin", target.user_id)
    assert result["status"] == "pending_ldap"
    assert target.locked_until is not None
    assert (await service.list("admin", status="pending_ldap"))["total"] == 1


async def test_ldap_identity_cannot_use_local_password_even_after_ldap_disabled(users):
    from testing_agent.schemas.auth import LoginRequest
    from testing_agent.services.auth import AuthService

    await LdapAccountService(users, auto_link=False).persist(IDENTITY, None)
    with pytest.raises(AppError) as error:
        await AuthService(users).login(LoginRequest(name="alice", password="anything"))
    assert error.value.code == 1024


async def test_pending_local_login_has_specific_error(users):
    from testing_agent.schemas.auth import LoginRequest
    from testing_agent.services.auth import AuthService

    await local(users)
    with pytest.raises(AppError) as error:
        await AuthService(users).login(LoginRequest(name="alice", password="anything"))
    assert error.value.code == 1023


async def test_enabled_ldap_rejects_registration_before_creating_local_user(users):
    from dataclasses import replace

    from testing_agent.core.config import Settings
    from testing_agent.core.ldap_config import LdapSettings
    from testing_agent.schemas.auth import RegisterRequest
    from testing_agent.services.auth import AuthService

    settings = replace(
        Settings.from_mapping({}),
        ldap=LdapSettings(
            enabled=True,
            server_url="ldap://directory.test",
            bind_dn="uid=reader,dc=test",
            bind_password="test",
            user_search_base="dc=test",
            access_group_dn="cn=group,dc=test",
        ),
    )
    with pytest.raises(AppError) as error:
        await AuthService(users, settings=settings).register(
            RegisterRequest(name="new-user", email="new@example.test", password="valid-password")
        )
    assert error.value.code == 1025
    assert await users.get_by_name("new-user") is None


async def test_rename_and_email_conflict_preserves_both_fields_and_token(users):
    service = LdapAccountService(users, auto_link=False)
    user = await service.persist(IDENTITY, None)
    user_id = user.user_id
    await local(users, user_id="occupied", nickname="occupied", email="occupied@test")
    changed = replace(IDENTITY, username="renamed", emails=("occupied@test",))
    snapshot = await service.snapshot(changed)
    await users.rollback()
    with pytest.raises(AppError) as error:
        await service.persist(changed, snapshot)
    assert error.value.http_code == 409
    current = await users.get_by_user_id(user_id)
    assert current.nickname == IDENTITY.username and current.email == IDENTITY.emails[0]
    assert current.token_version == 0


async def test_renamed_directory_identity_cannot_bypass_local_lock(users):
    service = LdapAccountService(users, auto_link=False)
    user = await service.persist(IDENTITY, None)
    user.locked_until = datetime.now(UTC) + timedelta(minutes=10)
    await users.commit()
    with pytest.raises(AppError) as error:
        await service.snapshot(replace(IDENTITY, username="renamed"))
    assert error.value.code == 1005

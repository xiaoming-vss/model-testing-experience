from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import Settings
from testing_agent.core.errors import AppError
from testing_agent.core.security import parse_access_token_claims
from testing_agent.models.revoked_access_token import RevokedAccessToken
from testing_agent.models.user import User
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.services.auth_session import SessionService, invalidate_sessions, issue_session


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(RevokedAccessToken.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(User(user_id="alice", nickname="alice", token_version=2, status="active"))
        await session.commit()
    yield factory
    await engine.dispose()


def settings() -> Settings:
    return Settings.from_mapping(
        {"security": {"jwt": {"key": "session-module-isolated-test-signing-key"}}}
    )


@pytest.mark.parametrize(
    "admin,ldap,hours", [(False, False, 72), (True, False, 24), (False, True, 12)]
)
def test_session_issuance_keeps_account_specific_expiry_and_independent_logins(admin, ldap, hours):
    config = settings()
    user = User(user_id="alice", is_super_admin=admin, token_version=7, must_change_password=True)
    first = issue_session(user, config, ldap=ldap)
    second = issue_session(user, config, ldap=ldap)
    assert first.access_token != second.access_token
    claims = parse_access_token_claims(first.access_token, config)
    assert claims.user_id == "alice" and claims.token_version == 7
    assert abs((claims.expires_at - datetime.now(UTC)).total_seconds() - hours * 3600) < 5
    assert first.must_change_password is (not ldap)


async def test_account_transaction_rollback_does_not_revoke_sessions(sessions):
    config = settings()
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.user_id == "alice"))
        token = issue_session(user, config).access_token
        invalidate_sessions(user)
        await session.flush()
        await session.rollback()
        service = SessionService(AuthSessionRepository(session), config)
        assert await service.authenticate(token, method="GET", path="/v1/projects") == "alice"
        user = await session.scalar(select(User).where(User.user_id == "alice"))
        invalidate_sessions(user)
        await session.commit()
        with pytest.raises(AppError) as error:
            await service.authenticate(token, method="GET", path="/v1/projects")
        assert error.value.http_code == 401


async def test_logout_cannot_revoke_another_users_session(sessions):
    config = settings()
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.user_id == "alice"))
        token = issue_session(user, config).access_token
        service = SessionService(AuthSessionRepository(session), config)
        with pytest.raises(AppError) as error:
            await service.logout("bob", token)
        assert error.value.http_code == 401
        assert await service.authenticate(token, method="GET", path="/v1/user") == "alice"
        assert await session.scalar(select(RevokedAccessToken)) is None

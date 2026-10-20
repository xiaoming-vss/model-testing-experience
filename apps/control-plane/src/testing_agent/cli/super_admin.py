"""Operational recovery for the single system super administrator.

Usage:
    python -m testing_agent.cli.super_admin reset-password --config config/local.toml
    python -m testing_agent.cli.super_admin reset-password \
        --config config/local.toml --password-stdin
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from testing_agent.core.config import load_settings
from testing_agent.core.security import hash_password
from testing_agent.domain.account_policy import validate_password
from testing_agent.models.login_rate_limit import LoginRateLimit
from testing_agent.models.user import User
from testing_agent.services.auth_session import invalidate_sessions


def _read_password(stdin: bool) -> str:
    if stdin:
        value = sys.stdin.readline().rstrip("\n")
        if not value:
            raise SystemExit("Password must not be empty")
        return value
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Confirm new password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    return first


async def _reset(config_path: str, password: str) -> None:
    settings = load_settings(config_path)
    if not settings.database_url:
        raise SystemExit("A database DSN is required")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            user = await session.scalar(
                select(User).where(User.is_super_admin.is_(True)).with_for_update()
            )
            if user is None:
                raise SystemExit(
                    "Super administrator does not exist; "
                    "start the control plane once to initialize it"
                )
            validate_password(password)
            user.password = hash_password(password)
            user.password_updated_at = datetime.now(UTC)
            user.must_change_password = True
            invalidate_sessions(user)
            user.failed_login_count = 0
            user.locked_until = None
            await session.execute(
                delete(LoginRateLimit).where(LoginRateLimit.username == user.nickname)
            )
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["reset-password"])
    parser.add_argument("--config", default="config/local.toml", help="control-plane config path")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the new password from standard input instead of a terminal prompt",
    )
    args = parser.parse_args()
    password = _read_password(args.password_stdin)
    asyncio.run(_reset(args.config, password))
    print("Super administrator password reset; all existing tokens are invalid.")


if __name__ == "__main__":
    main()

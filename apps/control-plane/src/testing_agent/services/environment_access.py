"""Personal ownership of explicitly secret environment values."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden
from testing_agent.models.api_environment_var import ApiEnvironmentVar


async def authorized_environment_vars(
    session: AsyncSession, user_id: str, environment_id: str
) -> list[ApiEnvironmentVar]:
    rows = list(
        (
            await session.scalars(
                select(ApiEnvironmentVar).where(ApiEnvironmentVar.environment_id == environment_id)
            )
        ).all()
    )
    for row in rows:
        if row.is_secret and row.secret_user_id != user_id:
            raise ErrForbidden
    return rows

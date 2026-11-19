"""Personal ownership of explicitly secret environment values."""

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.repositories.api_environment_var import ApiEnvironmentVarRepository


async def authorized_environment_vars(
    session: AsyncSession, user_id: str, environment_id: str
) -> list[ApiEnvironmentVar]:
    rows = await ApiEnvironmentVarRepository(session).list_by_environment(environment_id)
    for row in rows:
        if row.is_secret and row.secret_user_id != user_id:
            raise ErrForbidden()
    return rows

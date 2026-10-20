from sqlalchemy import select

from testing_agent.models.auth_runtime import AuthRuntime
from testing_agent.repositories.base import BaseRepository


class AuthRuntimeRepository(BaseRepository):
    async def get(self, *, for_update: bool = False) -> AuthRuntime | None:
        statement = select(AuthRuntime).where(AuthRuntime.id == 1)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement.execution_options(populate_existing=True))

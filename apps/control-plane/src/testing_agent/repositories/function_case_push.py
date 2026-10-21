"""Current reads for testcase identity and operation receipts; callers own transactions."""

from sqlalchemy import select

from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
    FunctionCaseRemoteIdentity,
)
from testing_agent.repositories.base import BaseRepository


class FunctionCasePushRepository(BaseRepository):
    async def identity(self, instance_key: str, case_id: str) -> FunctionCaseRemoteIdentity | None:
        return await self.session.scalar(
            select(FunctionCaseRemoteIdentity)
            .where(
                FunctionCaseRemoteIdentity.instance_key == instance_key,
                FunctionCaseRemoteIdentity.case_id == case_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def by_request(
        self, actor: str, request_id: str, case_id: str
    ) -> FunctionCasePushOperation | None:
        return await self.session.scalar(
            select(FunctionCasePushOperation)
            .where(
                FunctionCasePushOperation.actor_user_id == actor,
                FunctionCasePushOperation.request_id == request_id,
                FunctionCasePushOperation.case_id == case_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def active(self, active_key: str) -> FunctionCasePushOperation | None:
        return await self.session.scalar(
            select(FunctionCasePushOperation)
            .where(FunctionCasePushOperation.active_key == active_key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def operation(self, operation_id: str) -> FunctionCasePushOperation | None:
        return await self.session.scalar(
            select(FunctionCasePushOperation)
            .where(FunctionCasePushOperation.operation_id == operation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def identity_by_id(self, identity_id: int) -> FunctionCaseRemoteIdentity | None:
        return await self.session.scalar(
            select(FunctionCaseRemoteIdentity)
            .where(FunctionCaseRemoteIdentity.id == identity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

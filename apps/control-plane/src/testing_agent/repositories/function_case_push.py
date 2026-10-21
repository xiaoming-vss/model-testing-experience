"""Current reads for testcase identity and operation receipts; callers own transactions."""

from sqlalchemy import select

from testing_agent.models.function_case_push import (
    FunctionCasePushOperation,
    FunctionCasePushRequest,
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

    async def operation(
        self, operation_id: str, *, lock: bool = True
    ) -> FunctionCasePushOperation | None:
        statement = select(FunctionCasePushOperation).where(
            FunctionCasePushOperation.operation_id == operation_id
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement.execution_options(populate_existing=True))

    async def identity_by_id(self, identity_id: int) -> FunctionCaseRemoteIdentity | None:
        return await self.session.scalar(
            select(FunctionCaseRemoteIdentity)
            .where(FunctionCaseRemoteIdentity.id == identity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def request(
        self, actor: str, request_id: str, *, lock: bool = False
    ) -> FunctionCasePushRequest | None:
        statement = select(FunctionCasePushRequest).where(
            FunctionCasePushRequest.actor_user_id == actor,
            FunctionCasePushRequest.request_id == request_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement.execution_options(populate_existing=True))

    async def identities_for(
        self, project_id: str, instance_key: str, case_ids: list[str]
    ) -> list[FunctionCaseRemoteIdentity]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionCaseRemoteIdentity).where(
                        FunctionCaseRemoteIdentity.project_id == project_id,
                        FunctionCaseRemoteIdentity.case_id.in_(case_ids),
                        FunctionCaseRemoteIdentity.instance_key == instance_key,
                    )
                )
            ).all()
        )

    async def pending_for(
        self, project_id: str, case_ids: list[str]
    ) -> list[FunctionCasePushOperation]:
        return list(
            (
                await self.session.scalars(
                    select(FunctionCasePushOperation).where(
                        FunctionCasePushOperation.project_id == project_id,
                        FunctionCasePushOperation.case_id.in_(case_ids),
                        FunctionCasePushOperation.active_key.is_not(None),
                    )
                )
            ).all()
        )

    async def restore_reviewers(
        self,
        project_id: str,
        instance_key: str,
        restore_id: str,
        case_ids: list[str],
    ) -> dict[str, str]:
        rows = (
            await self.session.execute(
                select(FunctionCasePushOperation.case_id, FunctionCasePushOperation.target_json)
                .join(
                    FunctionCaseRemoteIdentity,
                    FunctionCaseRemoteIdentity.id == FunctionCasePushOperation.identity_id,
                )
                .where(
                    FunctionCasePushOperation.project_id == project_id,
                    FunctionCaseRemoteIdentity.instance_key == instance_key,
                    FunctionCasePushOperation.case_id.in_(case_ids),
                    FunctionCasePushOperation.status.in_(["succeeded", "failed"]),
                    FunctionCasePushOperation.target_json["_restoreId"].as_string() == restore_id,
                )
                .order_by(FunctionCasePushOperation.id.desc())
            )
        ).all()
        result: dict[str, str] = {}
        for case_id, target in rows:
            if target.get("_restoreConfirmedBy"):
                result.setdefault(case_id, str(target["_restoreConfirmedBy"]))
        return result

"""Restored databases stay fenced even if an old application/configuration is started."""

import hashlib
from hmac import compare_digest

from sqlalchemy import select

from testing_agent.core.errors import AppError, ErrUnauthorized
from testing_agent.models.integration_job import IntegrationRestoreReview, IntegrationRuntime


def key_digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def restored_runtime(session):
    return await session.scalar(select(IntegrationRuntime).where(IntegrationRuntime.id == 1))


async def isolated_scope(session, bug_id):
    return (
        await session.scalar(
            select(IntegrationRestoreReview.review_id)
            .join(
                IntegrationRuntime,
                IntegrationRuntime.restore_id == IntegrationRestoreReview.restore_id,
            )
            .where(
                IntegrationRuntime.id == 1,
                IntegrationRestoreReview.scope_type == "bug",
                IntegrationRestoreReview.scope_id == bug_id,
                IntegrationRestoreReview.decision == "isolated",
            )
            .limit(1)
        )
        is not None
    )


async def require_runtime(session, settings, *, worker=False):
    state = await restored_runtime(session)
    if state is None:
        return
    if (
        state.runtime_generation != settings.integration_execution.runtime_generation
        or not compare_digest(state.worker_key_digest, key_digest(settings.integration_worker_key))
    ):
        if worker:
            raise ErrUnauthorized()
        raise AppError(409, "恢复环境运行代次或专属令牌不匹配，请使用恢复配置", 409)
    if state.blocked:
        raise AppError(409, "恢复环境的外部集成尚未核对，已暂停所有远端写入", 409)

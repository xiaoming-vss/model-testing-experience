"""Project direct requirement-stage history to the existing paginated response."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.direct_history_projection import project_direct_history
from testing_agent.repositories.direct_attempt_history import direct_history_rows


async def direct_history(
    session: AsyncSession,
    task_id: str | None,
    page: int,
    page_size: int,
    pipeline_filter: str = "all",
    *,
    task_conditions: tuple = (),
) -> dict[str, Any]:
    rows = await direct_history_rows(
        session, task_id, page, page_size, pipeline_filter, task_conditions=task_conditions
    )
    return project_direct_history(*rows)

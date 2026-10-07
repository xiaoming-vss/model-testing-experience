"""Load display-only bindings for an already authorized resource list."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.schemas.resource_binding import ZentaoBindingSummaryResponse


async def load_zentao_binding_summaries(
    session: AsyncSession, resource_type: str, resource_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    rows = await ResourceBindingRepository(session).list_zentao_summaries(
        resource_type, resource_ids
    )
    summaries = {}
    for row in rows:
        resource_id = row["local_resource_id"]
        if resource_id not in summaries:
            summaries[resource_id] = ZentaoBindingSummaryResponse.model_validate(row).model_dump(
                by_alias=True
            )
    return summaries

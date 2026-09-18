"""Resolve API run ownership through the current collection."""

from sqlalchemy import select

from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint

FIELDS = ("requirement_id", "sprint_id", "project_id")


class ApiRunScopeRepositoryMixin:
    async def get_run_scope(self, run):
        scope = (
            await self.session.execute(
                select(ApiCollection.requirement_id, Requirement.sprint_id, Sprint.project_id)
                .join(Requirement, Requirement.requirement_id == ApiCollection.requirement_id)
                .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                .where(ApiCollection.collection_id == run.collection_id)
            )
        ).first()
        if scope is not None:
            return dict(zip(FIELDS, scope, strict=True))
        return None

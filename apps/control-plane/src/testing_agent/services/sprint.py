from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from testing_agent.core.enums import SprintStatus
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrNotFound,
    ErrSprintNameAlreadyUse,
    ErrSprintScheduleInvalid,
)
from testing_agent.core.sid import new_id
from testing_agent.core.utc import as_utc
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.schemas.sprint import CreateSprintRequest, SprintResponse, UpdateSprintRequest
from testing_agent.services.binding_summary import load_zentao_binding_summaries
from testing_agent.services.common import list_payload
from testing_agent.services.project import ProjectService
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


def derive_sprint_status(
    start_time: datetime, end_time: datetime, *, now: datetime | None = None
) -> SprintStatus:
    current_time = as_utc(now or datetime.now(UTC))
    if current_time < as_utc(start_time):
        return SprintStatus.PLANNED
    if current_time < as_utc(end_time):
        return SprintStatus.RUNNING
    return SprintStatus.COMPLETED


def dump_sprint(sprint: Sprint, *, now: datetime | None = None) -> dict:
    start_time = as_utc(sprint.start_time)
    end_time = as_utc(sprint.end_time)
    response = SprintResponse(
        sprint_id=sprint.sprint_id,
        project_id=sprint.project_id,
        name=sprint.name,
        description=sprint.description,
        status=derive_sprint_status(start_time, end_time, now=now),
        start_time=start_time,
        end_time=end_time,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
    )
    return response.model_dump(by_alias=True, mode="json")


def validate_schedule(start_time: datetime, end_time: datetime) -> None:
    if as_utc(end_time) <= as_utc(start_time):
        raise ErrSprintScheduleInvalid()


class SprintService:
    def __init__(
        self,
        sprints: SprintRepository,
        projects: ProjectService,
        *,
        deletion: ResourceDeletion | None = None,
    ) -> None:
        self.deletion = deletion or SqlResourceDeletion()
        self.sprints = sprints
        self.projects = projects

    async def get_accessible_entity(
        self, user_id: str, sprint_id: str, *, action: ProjectAction = "read"
    ) -> Sprint:
        sprint = await self.sprints.get_active_by_id(sprint_id)
        if sprint is None:
            raise ErrNotFound()
        await self.projects.get_accessible_entity(user_id, sprint.project_id, action=action)
        return sprint

    async def create(self, user_id: str, project_id: str, body: CreateSprintRequest) -> dict:
        await self.projects.get_accessible_entity(user_id, project_id, action="write")
        exists = await self.sprints.get_active_by_project_and_name(project_id, body.name)
        if exists is not None:
            raise ErrSprintNameAlreadyUse()
        sprint = Sprint(
            sprint_id=new_id(),
            project_id=project_id,
            name=body.name,
            description=body.description,
            start_time=body.start_time,
            end_time=body.end_time,
        )
        self.sprints.add(sprint)
        await self.sprints.commit()
        await self.sprints.refresh(sprint)
        return dump_sprint(sprint)

    async def list(self, user_id: str, project_id: str) -> dict[str, Any]:
        await self.projects.get_accessible_entity(user_id, project_id, action="read")
        rows = await self.sprints.list_active_by_project(project_id)
        bindings = await load_zentao_binding_summaries(
            self.sprints.session, "sprint", [row.sprint_id for row in rows]
        )
        return list_payload(
            [{**dump_sprint(row), "zentaoBinding": bindings.get(row.sprint_id)} for row in rows]
        )

    async def get(self, user_id: str, sprint_id: str) -> dict:
        return dump_sprint(await self.get_accessible_entity(user_id, sprint_id, action="read"))

    async def update(self, user_id: str, sprint_id: str, body: UpdateSprintRequest) -> dict:
        sprint = await self.get_accessible_entity(user_id, sprint_id, action="write")
        fields = body.model_fields_set
        start_time = sprint.start_time
        end_time = sprint.end_time
        if "start_time" in fields:
            if body.start_time is None:
                raise ErrBadRequest()
            start_time = body.start_time
        if "end_time" in fields:
            if body.end_time is None:
                raise ErrBadRequest()
            end_time = body.end_time
        validate_schedule(start_time, end_time)
        if "name" in fields:
            if body.name is None:
                raise ErrBadRequest()
            sprint.name = body.name
        if "description" in fields:
            if body.description is None:
                raise ErrBadRequest()
            sprint.description = body.description
        sprint.start_time = start_time
        sprint.end_time = end_time
        await self.sprints.commit()
        await self.sprints.refresh(sprint)
        return dump_sprint(sprint)

    async def delete(self, user_id: str, sprint_id: str) -> dict:
        sprint = await self.get_accessible_entity(user_id, sprint_id, action="write")
        await self.deletion.delete(self.sprints.session, sprint)
        await self.sprints.commit()
        return {}

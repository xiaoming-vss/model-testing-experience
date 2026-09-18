from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.sprint import (
    create_sprint,
    delete_sprint,
    get_sprint,
    list_sprints,
    update_sprint,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.sprint import SprintResponse

router = APIRouter()

router.post("/projects/{project_id}/sprints", response_model=ApiResponse[SprintResponse])(
    create_sprint
)
router.get(
    "/projects/{project_id}/sprints",
    response_model=ApiResponse[ListResponse[SprintResponse]],
)(list_sprints)
router.get("/sprints/{sprint_id}", response_model=ApiResponse[SprintResponse])(get_sprint)
router.patch("/sprints/{sprint_id}", response_model=ApiResponse[SprintResponse])(update_sprint)
router.delete("/sprints/{sprint_id}", response_model=ApiResponse[EmptyData])(delete_sprint)

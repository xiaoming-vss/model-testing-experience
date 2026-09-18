from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.project import (
    add_project_member,
    change_project_member,
    create_project,
    delete_project,
    get_project,
    leave_project,
    list_project_members,
    list_projects,
    remove_project_member,
    transfer_project,
    update_project,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.project import ProjectResponse
from testing_agent.schemas.project_member import ProjectMemberResponse

router = APIRouter()

router.post("/projects", response_model=ApiResponse[ProjectResponse])(create_project)
router.get("/projects", response_model=ApiResponse[ListResponse[ProjectResponse]])(list_projects)
router.get("/projects/{project_id}", response_model=ApiResponse[ProjectResponse])(get_project)
router.patch("/projects/{project_id}", response_model=ApiResponse[ProjectResponse])(update_project)
router.delete("/projects/{project_id}", response_model=ApiResponse[EmptyData])(delete_project)

router.post("/projects/{project_id}/members", response_model=ApiResponse[ProjectMemberResponse])(
    add_project_member
)
router.get(
    "/projects/{project_id}/members",
    response_model=ApiResponse[ListResponse[ProjectMemberResponse]],
)(list_project_members)

router.patch("/projects/{project_id}/members/{member_id}", response_model=ApiResponse[EmptyData])(
    change_project_member
)
router.delete("/projects/{project_id}/members/{member_id}", response_model=ApiResponse[EmptyData])(
    remove_project_member
)
router.post("/projects/{project_id}/leave", response_model=ApiResponse[EmptyData])(leave_project)
router.post(
    "/projects/{project_id}/transfer-ownership", response_model=ApiResponse[ProjectResponse]
)(transfer_project)

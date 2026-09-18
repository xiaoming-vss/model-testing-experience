from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.project_skill_space import (
    create_project_skill,
    delete_project_skill,
    download_project_skill,
    list_project_skills,
)
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.project_skill_space import ProjectSkillSpaceResponse

router = APIRouter()

router.get(
    "/projects/{project_id}/skills",
    response_model=ApiResponse[ListResponse[ProjectSkillSpaceResponse]],
)(list_project_skills)
router.post(
    "/projects/{project_id}/skills",
    response_model=ApiResponse[ProjectSkillSpaceResponse],
)(create_project_skill)
router.delete(
    "/projects/{project_id}/skills/{skill_space_id}",
    response_model=ApiResponse[EmptyData],
)(delete_project_skill)
router.get(
    "/projects/{project_id}/skills/{skill_space_id}/download",
    response_model=ApiResponse[ProjectSkillSpaceResponse],
)(download_project_skill)

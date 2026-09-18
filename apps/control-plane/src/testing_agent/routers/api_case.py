from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_case import (
    create_api_case,
    delete_api_case,
    get_api_case,
    list_api_cases,
    update_api_case,
)
from testing_agent.schemas.api_case import ApiCaseResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/api-collections/{collection_id}/cases",
    response_model=ApiResponse[ApiCaseResponse],
)(create_api_case)
router.get(
    "/api-collections/{collection_id}/cases",
    response_model=ApiResponse[ListResponse[ApiCaseResponse]],
)(list_api_cases)
router.get("/api-cases/{case_id}", response_model=ApiResponse[ApiCaseResponse])(get_api_case)
router.patch("/api-cases/{case_id}", response_model=ApiResponse[ApiCaseResponse])(update_api_case)
router.delete("/api-cases/{case_id}", response_model=ApiResponse[EmptyData])(delete_api_case)

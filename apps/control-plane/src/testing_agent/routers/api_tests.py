from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.api_assert_rule import (
    create_api_assert_rule,
    delete_api_assert_rule,
    get_api_assert_rule,
    list_api_assert_rules,
    update_api_assert_rule,
)
from testing_agent.handlers.api_collection import (
    create_api_collection,
    delete_api_collection,
    get_api_collection,
    import_api_cases,
    list_api_collections,
    update_api_collection,
)
from testing_agent.handlers.api_environment import (
    create_api_environment,
    delete_api_environment,
    get_api_environment,
    list_api_environments,
    update_api_environment,
)
from testing_agent.handlers.api_environment_var import (
    create_api_environment_var,
    delete_api_environment_var,
    get_api_environment_var,
    list_api_environment_vars,
    update_api_environment_var,
)
from testing_agent.handlers.api_extract_rule import (
    create_api_extract_rule,
    delete_api_extract_rule,
    get_api_extract_rule,
    list_api_extract_rules,
    update_api_extract_rule,
)
from testing_agent.schemas.api_assert_rule import ApiAssertRuleResponse
from testing_agent.schemas.api_collection import (
    ApiCollectionImportResponse,
    ApiCollectionResponse,
)
from testing_agent.schemas.api_environment import ApiEnvironmentResponse
from testing_agent.schemas.api_environment_var import ApiEnvironmentVarResponse
from testing_agent.schemas.api_extract_rule import ApiExtractRuleResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse

router = APIRouter()

router.post(
    "/requirements/{requirement_id}/api-collections",
    response_model=ApiResponse[ApiCollectionResponse],
)(create_api_collection)
router.get(
    "/requirements/{requirement_id}/api-collections",
    response_model=ApiResponse[ListResponse[ApiCollectionResponse]],
)(list_api_collections)
router.get(
    "/api-collections/{collection_id}",
    response_model=ApiResponse[ApiCollectionResponse],
)(get_api_collection)
router.patch(
    "/api-collections/{collection_id}",
    response_model=ApiResponse[ApiCollectionResponse],
)(update_api_collection)
router.delete(
    "/api-collections/{collection_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_collection)
router.post(
    "/api-collections/{collection_id}/import",
    response_model=ApiResponse[ApiCollectionImportResponse],
)(import_api_cases)
router.post(
    "/api-cases/{case_id}/assert-rules",
    response_model=ApiResponse[ApiAssertRuleResponse],
)(create_api_assert_rule)
router.get(
    "/api-cases/{case_id}/assert-rules",
    response_model=ApiResponse[ListResponse[ApiAssertRuleResponse]],
)(list_api_assert_rules)
router.get(
    "/api-assert-rules/{assert_rule_id}",
    response_model=ApiResponse[ApiAssertRuleResponse],
)(get_api_assert_rule)
router.patch(
    "/api-assert-rules/{assert_rule_id}",
    response_model=ApiResponse[ApiAssertRuleResponse],
)(update_api_assert_rule)
router.delete(
    "/api-assert-rules/{assert_rule_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_assert_rule)
router.post(
    "/api-cases/{case_id}/extract-rules",
    response_model=ApiResponse[ApiExtractRuleResponse],
)(create_api_extract_rule)
router.get(
    "/api-cases/{case_id}/extract-rules",
    response_model=ApiResponse[ListResponse[ApiExtractRuleResponse]],
)(list_api_extract_rules)
router.get(
    "/api-extract-rules/{extract_rule_id}",
    response_model=ApiResponse[ApiExtractRuleResponse],
)(get_api_extract_rule)
router.patch(
    "/api-extract-rules/{extract_rule_id}",
    response_model=ApiResponse[ApiExtractRuleResponse],
)(update_api_extract_rule)
router.delete(
    "/api-extract-rules/{extract_rule_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_extract_rule)
router.post(
    "/projects/{project_id}/api-environments",
    response_model=ApiResponse[ApiEnvironmentResponse],
)(create_api_environment)
router.get(
    "/projects/{project_id}/api-environments",
    response_model=ApiResponse[ListResponse[ApiEnvironmentResponse]],
)(list_api_environments)
router.get(
    "/api-environments/{environment_id}",
    response_model=ApiResponse[ApiEnvironmentResponse],
)(get_api_environment)
router.patch(
    "/api-environments/{environment_id}",
    response_model=ApiResponse[ApiEnvironmentResponse],
)(update_api_environment)
router.delete(
    "/api-environments/{environment_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_environment)
router.post(
    "/api-environments/{environment_id}/vars",
    response_model=ApiResponse[ApiEnvironmentVarResponse],
)(create_api_environment_var)
router.get(
    "/api-environments/{environment_id}/vars",
    response_model=ApiResponse[ListResponse[ApiEnvironmentVarResponse]],
)(list_api_environment_vars)
router.get(
    "/api-environment-vars/{env_var_id}",
    response_model=ApiResponse[ApiEnvironmentVarResponse],
)(get_api_environment_var)
router.patch(
    "/api-environment-vars/{env_var_id}",
    response_model=ApiResponse[ApiEnvironmentVarResponse],
)(update_api_environment_var)
router.delete(
    "/api-environment-vars/{env_var_id}",
    response_model=ApiResponse[EmptyData],
)(delete_api_environment_var)

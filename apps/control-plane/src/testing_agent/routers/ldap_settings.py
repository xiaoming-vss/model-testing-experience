from fastapi import APIRouter

from testing_agent.handlers.ldap_settings import get_config, save_config, test_config
from testing_agent.schemas.common import ApiResponse
from testing_agent.schemas.ldap_settings import LdapSettingsResponse, LdapTestResponse

router = APIRouter()
router.get("/admin/ldap", response_model=ApiResponse[LdapSettingsResponse])(get_config)
router.put("/admin/ldap", response_model=ApiResponse[LdapSettingsResponse])(save_config)
router.post(
    "/admin/ldap/test",
    response_model=ApiResponse[LdapTestResponse],
    response_model_exclude_none=True,
)(test_config)

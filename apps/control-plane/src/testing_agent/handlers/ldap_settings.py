from fastapi import Depends

from testing_agent.api.deps import get_ldap_settings_service, require_super_admin
from testing_agent.core.errors import success_payload
from testing_agent.schemas.ldap_settings import SaveLdapRequest, TestLdapRequest
from testing_agent.services.ldap_settings import LdapSettingsService


async def get_config(
    actor_id: str = Depends(require_super_admin),
    service: LdapSettingsService = Depends(get_ldap_settings_service),
) -> dict:
    return success_payload(await service.read(actor_id))


async def save_config(
    body: SaveLdapRequest,
    actor_id: str = Depends(require_super_admin),
    service: LdapSettingsService = Depends(get_ldap_settings_service),
) -> dict:
    return success_payload(
        await service.save(
            actor_id, body.generation, body.config.configuration(), body.clearPassword
        )
    )


async def test_config(
    body: TestLdapRequest,
    actor_id: str = Depends(require_super_admin),
    service: LdapSettingsService = Depends(get_ldap_settings_service),
) -> dict:
    return success_payload(
        await service.test(actor_id, body.config.configuration(), body.username, body.clearPassword)
    )

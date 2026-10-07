from typing import Annotated

from pydantic import Field

from testing_agent.schemas.integration_job import Identifier, IntegrationProtocolModel


class IntegrationRestoreAudit(IntegrationProtocolModel):
    restore_id: Identifier
    bug_id: Identifier
    actor_user_id: Identifier
    remote_bug_id: int = Field(gt=0, le=2_147_483_647, strict=True)
    files: dict[Identifier, Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]] = Field(
        default_factory=dict, max_length=1000
    )


class IntegrationRestoreIsolation(IntegrationProtocolModel):
    restore_id: Identifier
    bug_id: Identifier | None = None
    job_id: Identifier | None = None

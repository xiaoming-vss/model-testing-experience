from testing_agent.schemas.bug_zentao_push import BugZentaoPushRequest, BugZentaoUpdateRequest
from testing_agent.schemas.integration_job import Identifier
from testing_agent.schemas.integration_job import IntegrationJobSummary as IntegrationJobSummary


class IntegrationSyncRequest(BugZentaoPushRequest):
    request_id: Identifier


class IntegrationFieldsRequest(BugZentaoUpdateRequest):
    request_id: Identifier

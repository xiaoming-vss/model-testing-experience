"""已关联 Bug 从禅道拉取更新的 HTTP 入口。"""

from fastapi import Depends

from testing_agent.api.deps import (
    get_bug_service,
    get_current_user_id,
    get_integration_connection_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.bug_zentao_pull import ZentaoPullRequest
from testing_agent.services.bug import BugService
from testing_agent.services.bug_zentao_pull import BugZentaoPullService
from testing_agent.services.integration_connection import IntegrationConnectionService


def service(
    bugs: BugService = Depends(get_bug_service),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return BugZentaoPullService(bugs, connections)


async def get_bug_zentao_remote(
    bug_id: str,
    user_id: str = Depends(get_current_user_id),
    pulls: BugZentaoPullService = Depends(service),
):
    return success_payload(await pulls.preview(user_id, bug_id))


async def pull_bug_zentao(
    bug_id: str,
    body: ZentaoPullRequest,
    user_id: str = Depends(get_current_user_id),
    pulls: BugZentaoPullService = Depends(service),
):
    return success_payload(await pulls.apply(user_id, bug_id, body))

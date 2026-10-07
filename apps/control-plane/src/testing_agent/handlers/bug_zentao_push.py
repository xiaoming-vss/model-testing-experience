from fastapi import Depends

from testing_agent.api.deps import (
    get_bug_service,
    get_current_user_id,
    get_integration_bug_service,
    get_integration_connection_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.bug_zentao_push import (
    BugZentaoAttachmentReconcileRequest,
    BugZentaoReconcileRequest,
)
from testing_agent.services.bug import BugService
from testing_agent.services.bug_zentao_attachment import BugZentaoAttachmentService
from testing_agent.services.bug_zentao_push import BugZentaoPushService
from testing_agent.services.integration_connection import IntegrationConnectionService


def service(
    bugs: BugService = Depends(get_bug_service),
    connections: IntegrationConnectionService = Depends(get_integration_connection_service),
):
    return BugZentaoPushService(bugs, connections)


async def get_bug_zentao_push(
    bug_id: str,
    user_id: str = Depends(get_current_user_id),
    integration=Depends(get_integration_bug_service),
):
    return success_payload(await integration.status(user_id, bug_id))


async def get_bug_zentao_push_options(
    bug_id: str,
    user_id: str = Depends(get_current_user_id),
    pushes: BugZentaoPushService = Depends(service),
):
    return success_payload(await pushes.options(user_id, bug_id))


async def reconcile_bug_zentao_push(
    bug_id: str,
    body: BugZentaoReconcileRequest,
    user_id: str = Depends(get_current_user_id),
    pushes: BugZentaoPushService = Depends(service),
    integration=Depends(get_integration_bug_service),
):
    await integration.guard_recovery(user_id, bug_id)
    await pushes.reconcile(user_id, bug_id, body.remote_bug_id)
    return success_payload(await integration.status(user_id, bug_id))


async def reconcile_bug_attachment(
    bug_id: str,
    file_id: str,
    body: BugZentaoAttachmentReconcileRequest,
    user_id: str = Depends(get_current_user_id),
    pushes: BugZentaoPushService = Depends(service),
    integration=Depends(get_integration_bug_service),
):
    await integration.guard_recovery(user_id, bug_id)
    await BugZentaoAttachmentService(pushes).reconcile(
        user_id, bug_id, file_id, body.remote_file_id
    )
    return success_payload(await integration.status(user_id, bug_id))

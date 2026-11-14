"""Browser entry points for case visualization."""

from fastapi import Depends

from testing_agent.api.deps import get_case_visualization_service, get_current_user_id
from testing_agent.core.errors import success_payload
from testing_agent.schemas.case_visualization import (
    VisualizationBatchRequest,
    VisualizationLookup,
    VisualizationRequest,
)
from testing_agent.services.test_order_case_visualization import TestOrderCaseVisualizationService


async def get_visualization(
    order_id: str,
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderCaseVisualizationService = Depends(get_case_visualization_service),
):
    return success_payload(await service.get(user_id, order_id, entry_id))


async def dispatch_visualization(
    order_id: str,
    entry_id: str,
    body: VisualizationRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderCaseVisualizationService = Depends(get_case_visualization_service),
):
    return success_payload(await service.dispatch(user_id, order_id, entry_id, body.model_dump()))


async def lookup_visualizations(
    order_id: str,
    body: VisualizationLookup,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderCaseVisualizationService = Depends(get_case_visualization_service),
):
    return success_payload(await service.lookup(user_id, order_id, body.entry_ids))


async def dispatch_visualization_batch(
    order_id: str,
    body: VisualizationBatchRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderCaseVisualizationService = Depends(get_case_visualization_service),
):
    return success_payload(await service.batch_dispatch(user_id, order_id, body.model_dump()))


async def get_visualization_batch(
    order_id: str,
    batch_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderCaseVisualizationService = Depends(get_case_visualization_service),
):
    return success_payload(await service.get_batch(user_id, order_id, batch_id))

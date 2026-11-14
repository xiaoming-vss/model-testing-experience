from fastapi import APIRouter

from testing_agent.handlers.case_visualization import (
    dispatch_visualization,
    dispatch_visualization_batch,
    get_visualization,
    get_visualization_batch,
    lookup_visualizations,
)
from testing_agent.schemas.case_visualization import (
    VisualizationBatchResponse,
    VisualizationReceipt,
    VisualizationResponse,
)
from testing_agent.schemas.common import ApiResponse, ListResponse

router = APIRouter()
router.get(
    "/test-orders/{order_id}/entries/{entry_id}/visualization",
    response_model=ApiResponse[VisualizationResponse],
)(get_visualization)
router.post(
    "/test-orders/{order_id}/entries/{entry_id}/visualization/runs",
    response_model=ApiResponse[VisualizationReceipt],
)(dispatch_visualization)
router.post(
    "/test-orders/{order_id}/visualizations/lookup",
    response_model=ApiResponse[ListResponse[VisualizationResponse]],
)(lookup_visualizations)
router.post(
    "/test-orders/{order_id}/visualization-batches",
    response_model=ApiResponse[VisualizationBatchResponse],
)(dispatch_visualization_batch)
router.get(
    "/test-orders/{order_id}/visualization-batches/{batch_id}",
    response_model=ApiResponse[VisualizationBatchResponse],
)(get_visualization_batch)

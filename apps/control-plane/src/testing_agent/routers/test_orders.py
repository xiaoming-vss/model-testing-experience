from __future__ import annotations

from fastapi import APIRouter

from testing_agent.handlers.test_order import (
    add_test_order_cases,
    assign_test_order_entries,
    batch_mark_test_order_entries,
    create_test_order,
    delete_test_order,
    delete_test_order_entry,
    dispatch_test_order_graph,
    get_test_order,
    get_test_order_graph,
    get_test_order_graph_input,
    list_project_test_orders,
    list_test_order_entries,
    update_test_order,
    update_test_order_entry,
)
from testing_agent.schemas.ai_generate_task import AiGenerateTaskRunResponse
from testing_agent.schemas.common import ApiResponse, EmptyData, ListResponse
from testing_agent.schemas.test_order import (
    TestOrderAddCasesResponse,
    TestOrderEntriesBatchMarkResponse,
    TestOrderEntryResponse,
    TestOrderGraphInputResponse,
    TestOrderGraphResponse,
    TestOrderResponse,
)

router = APIRouter()

router.post(
    "/sprints/{sprint_id}/test-orders",
    response_model=ApiResponse[TestOrderResponse],
)(create_test_order)
router.get(
    "/projects/{project_id}/test-orders",
    response_model=ApiResponse[ListResponse[TestOrderResponse]],
)(list_project_test_orders)
router.get(
    "/test-orders/{order_id}",
    response_model=ApiResponse[TestOrderResponse],
)(get_test_order)
router.patch(
    "/test-orders/{order_id}",
    response_model=ApiResponse[TestOrderResponse],
)(update_test_order)
router.delete(
    "/test-orders/{order_id}",
    response_model=ApiResponse[EmptyData],
)(delete_test_order)
router.get(
    "/test-orders/{order_id}/entries",
    response_model=ApiResponse[ListResponse[TestOrderEntryResponse]],
)(list_test_order_entries)
router.post(
    "/test-orders/{order_id}/cases",
    response_model=ApiResponse[TestOrderAddCasesResponse],
)(add_test_order_cases)
router.patch(
    "/test-orders/{order_id}/entries/{entry_id}",
    response_model=ApiResponse[TestOrderEntryResponse],
)(update_test_order_entry)
router.post(
    "/test-orders/{order_id}/entries/batch-mark-passed",
    response_model=ApiResponse[TestOrderEntriesBatchMarkResponse],
)(batch_mark_test_order_entries)
router.post(
    "/test-orders/{order_id}/entries/assign",
    response_model=ApiResponse[ListResponse[TestOrderEntryResponse]],
)(assign_test_order_entries)
router.delete(
    "/test-orders/{order_id}/entries/{entry_id}",
    response_model=ApiResponse[EmptyData],
)(delete_test_order_entry)
router.post(
    "/test-orders/{order_id}/graph-analysis",
    response_model=ApiResponse[AiGenerateTaskRunResponse],
)(dispatch_test_order_graph)
router.get(
    "/test-orders/{order_id}/graph-analysis",
    response_model=ApiResponse[TestOrderGraphResponse],
)(get_test_order_graph)
router.get(
    "/test-orders/{order_id}/graph-input",
    response_model=ApiResponse[TestOrderGraphInputResponse],
)(get_test_order_graph_input)

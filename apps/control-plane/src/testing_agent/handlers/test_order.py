from __future__ import annotations

from fastapi import Depends, Query

from testing_agent.api.deps import (
    get_current_user_id,
    get_test_order_entry_service,
    get_test_order_graph_service,
    get_test_order_service,
)
from testing_agent.core.errors import success_payload
from testing_agent.schemas.test_order import (
    TestOrderAddCasesRequest,
    TestOrderAssignRequest,
    TestOrderEntriesBatchMarkRequest,
    TestOrderEntryUpdateRequest,
    TestOrderGraphRequest,
    TestOrderRequest,
    TestOrderUpdateRequest,
)
from testing_agent.services.test_order import TestOrderService
from testing_agent.services.test_order_entry import TestOrderEntryService
from testing_agent.services.test_order_graph import TestOrderGraphService


async def create_test_order(
    sprint_id: str,
    body: TestOrderRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderService = Depends(get_test_order_service),
):
    return success_payload(await service.create(user_id, sprint_id, body))


async def list_project_test_orders(
    project_id: str,
    sprint_id: str = Query(default="", alias="sprintId"),
    user_id: str = Depends(get_current_user_id),
    service: TestOrderService = Depends(get_test_order_service),
):
    return success_payload(await service.list_project(user_id, project_id, sprint_id=sprint_id))


async def get_test_order(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderService = Depends(get_test_order_service),
):
    return success_payload(await service.get(user_id, order_id))


async def update_test_order(
    order_id: str,
    body: TestOrderUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderService = Depends(get_test_order_service),
):
    return success_payload(
        await service.update(user_id, order_id, body.model_dump(by_alias=True, exclude_none=True))
    )


async def delete_test_order(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderService = Depends(get_test_order_service),
):
    return success_payload(await service.delete(user_id, order_id))


async def list_test_order_entries(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(await service.list(user_id, order_id))


async def add_test_order_cases(
    order_id: str,
    body: TestOrderAddCasesRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(await service.add_cases(user_id, order_id, body.case_ids))


async def update_test_order_entry(
    order_id: str,
    entry_id: str,
    body: TestOrderEntryUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(
        await service.update(
            user_id, order_id, entry_id, body.model_dump(by_alias=False, exclude_none=True)
        )
    )


async def batch_mark_test_order_entries(
    order_id: str,
    body: TestOrderEntriesBatchMarkRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(await service.batch_mark_passed(user_id, order_id, body.entry_ids))


async def assign_test_order_entries(
    order_id: str,
    body: TestOrderAssignRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(
        await service.assign(user_id, order_id, body.entry_ids, body.assignee_user_id)
    )


async def delete_test_order_entry(
    order_id: str,
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderEntryService = Depends(get_test_order_entry_service),
):
    return success_payload(await service.delete(user_id, order_id, entry_id))


async def dispatch_test_order_graph(
    order_id: str,
    body: TestOrderGraphRequest,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderGraphService = Depends(get_test_order_graph_service),
):
    return success_payload(await service.dispatch(user_id, order_id, body.model_dump()))


async def get_test_order_graph(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderGraphService = Depends(get_test_order_graph_service),
):
    return success_payload(await service.get(user_id, order_id))


async def get_test_order_graph_input(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TestOrderGraphService = Depends(get_test_order_graph_service),
):
    return success_payload(await service.graph_input(user_id, order_id))

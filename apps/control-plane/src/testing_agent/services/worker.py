"""Worker protocol dispatch and credential payloads; execution rules live by domain."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.domain.worker_context import (
    ApiWorkerContext,
    UiWorkerContext,
    WorkerExecutionContext,
)
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.worker_context import read_worker_context
from testing_agent.schemas.workers import (
    WorkerTaskEventRequest,
)
from testing_agent.services.worker_domains import ai, api, ui
from testing_agent.services.worker_domains.ai import (
    apply_ai_completion_to_run as apply_ai_completion_to_run,
)
from testing_agent.services.worker_domains.api import (
    api_case_worker_snapshot as api_case_worker_snapshot,
)
from testing_agent.services.worker_domains.api import (
    extracted_environment_values as extracted_environment_values,
)
from testing_agent.services.worker_domains.api import (
    save_extracted_environment_vars as save_extracted_environment_vars,
)
from testing_agent.services.worker_domains.api import update_item_counts as update_item_counts
from testing_agent.services.worker_domains.events import LEASE_SECONDS as LEASE_SECONDS
from testing_agent.services.worker_domains.events import apply_event_to_task as apply_event_to_task
from testing_agent.services.worker_domains.events import final_run_status as final_run_status
from testing_agent.services.worker_domains.events import json_text as json_text
from testing_agent.services.worker_domains.events import parse_event_time as parse_event_time
from testing_agent.services.worker_domains.events import task_payload as task_payload
from testing_agent.services.worker_domains.events import update_task_claimed as update_task_claimed
from testing_agent.services.worker_domains.ui import ui_case_payload as ui_case_payload
from testing_agent.services.worker_domains.ui import ui_suite_payload as ui_suite_payload
from testing_agent.services.worker_domains.ui import update_ui_item_counts as update_ui_item_counts


def llm_credentials_payload(
    task_id: str,
    connection: IntegrationConnection | Any | None,
    cipher: Any | None = None,
) -> dict[str, Any]:
    if connection is None:
        return {"taskId": task_id, "baseUrl": "", "modelId": "", "apiKey": ""}
    secret = connection.secret_json or {}
    extra = connection.extra_json or {}
    api_key = secret.get("apiKey") or secret.get("api_key") or connection.access_token
    if api_key and cipher is not None:
        try:
            api_key = cipher.decrypt(api_key)
        except ValueError:
            # 凭据损坏(密钥轮换或手工改动):不下发,任务侧会因缺 key 失败并提示重配。
            api_key = ""
    model_id = (
        secret.get("modelId")
        or secret.get("model")
        or secret.get("model_id")
        or extra.get("modelId")
        or extra.get("model")
        or extra.get("model_id")
        or ""
    )
    return {
        "taskId": task_id,
        "connectionId": connection.connection_id,
        "baseUrl": connection.base_url,
        "modelId": model_id,
        "apiKey": api_key,
        "organization": extra.get("organization") or secret.get("organization") or "",
    }


def project_skill_worker_payload(skill: ProjectSkillSpace) -> dict[str, Any]:
    from testing_agent.services.project_skill_space import dump_skill

    return dump_skill(skill)


async def find_task(session: AsyncSession, domain: str, task_id: str) -> WorkerTask:
    task = await session.scalar(
        select(WorkerTask)
        .where(WorkerTask.domain == domain, WorkerTask.task_id == task_id)
        .with_for_update()
    )
    if task is None:
        raise ErrNotFound()
    return task


async def build_snapshot(
    session: AsyncSession,
    domain: str,
    task: WorkerTask,
    *,
    context: WorkerExecutionContext | None = None,
) -> dict[str, Any]:
    if domain == "ai":
        return await ai.build_snapshot(session, task)
    if context is None and domain in {"api", "ui"}:
        context = await session.run_sync(lambda sync: read_worker_context(sync, task))
    if domain == "api":
        if not isinstance(context, ApiWorkerContext):
            raise ErrBadRequest()
        return await api.build_snapshot(session, task, context)
    if domain == "ui":
        if not isinstance(context, UiWorkerContext):
            raise ErrBadRequest()
        return await ui.build_snapshot(session, task, context)
    return task_payload(task, context)


async def complete_domain_run(
    session: AsyncSession, domain: str, task: WorkerTask, body: WorkerTaskEventRequest
) -> None:
    if domain == "ai":
        await ai.complete_run(session, task, body)
    elif domain == "api":
        await api.complete_run(session, task, body)
    elif domain == "ui":
        await ui.complete_run(session, task, body)

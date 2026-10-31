"""Resolve and write environment values for a UI worker's current run."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrBadRequest, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.domain.variable_names import validate_variable_name
from testing_agent.models.api_environment import ApiEnvironment
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.worker_task import WorkerTask
from testing_agent.schemas.ui_variables import (
    ResolveUiRunVariablesRequest,
    WriteUiRunVariableResult,
    WriteUiRunVariablesRequest,
)
from testing_agent.services.ui_run_variable_records import record_variable_writes
from testing_agent.services.worker_authorization import authorize_execution
from testing_agent.services.worker_task import ensure_worker_match

BASE_URL_NAME = "baseUrl"
MAX_NAMES = 200
MAX_NAME_LENGTH = 120
MAX_WRITE_ITEMS = 200


class UiRunVariablesService:
    """Handler-facing facade so HTTP modules never touch the session or models."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, run_id: str, body: ResolveUiRunVariablesRequest) -> dict[str, Any]:
        return await resolve_run_variables(self.session, run_id, body)

    async def write(self, run_id: str, body: WriteUiRunVariablesRequest) -> dict[str, Any]:
        return await write_run_variables(self.session, run_id, body)


async def resolve_run_variables(
    session: AsyncSession, run_id: str, body: ResolveUiRunVariablesRequest
) -> dict[str, Any]:
    task = await _authorized_task(session, run_id, body)
    authority = await authorize_execution(session, task)
    environment = await _run_environment(session, authority.run)
    names = _normalize_names(body.names)

    values: dict[str, str] = {}
    secret_names: list[str] = []
    if names:
        rows = (
            await session.scalars(
                select(ApiEnvironmentVar).where(
                    ApiEnvironmentVar.environment_id == environment.environment_id,
                    ApiEnvironmentVar.var_key.in_(names),
                )
            )
        ).all()
        values = {row.var_key: row.value for row in rows}
        secret_names = [row.var_key for row in rows if row.is_secret]
    if BASE_URL_NAME in names:
        values[BASE_URL_NAME] = environment.base_url

    return {
        "values": values,
        "missing": [name for name in names if name not in values],
        "secret_names": secret_names,
    }


async def write_run_variables(
    session: AsyncSession, run_id: str, body: WriteUiRunVariablesRequest
) -> dict[str, Any]:
    """Update or create environment variables, then record the write on the run."""
    task = await _authorized_task(session, run_id, body)
    authority = await authorize_execution(session, task)
    environment = await _run_environment(session, authority.run)
    items = _normalize_write_items(body.items)

    results: list[WriteUiRunVariableResult] = []
    records: list[dict[str, Any]] = []
    for item in items:
        existing = await session.scalar(
            select(ApiEnvironmentVar).where(
                ApiEnvironmentVar.environment_id == environment.environment_id,
                ApiEnvironmentVar.var_key == item["name"],
            )
        )
        created = existing is None
        if existing is None:
            previous = ""
            secret = False
            masked_previous = None
            session.add(
                ApiEnvironmentVar(
                    env_var_id=new_id(),
                    environment_id=environment.environment_id,
                    var_key=item["name"],
                    value=item["value"],
                    description="",
                    is_secret=False,
                    secret_user_id="",
                )
            )
        else:
            previous = existing.value
            secret = bool(existing.is_secret)
            masked_previous = "********" if secret else previous
            existing.value = item["value"]
        results.append(
            WriteUiRunVariableResult(
                name=item["name"],
                created=created,
                previous_value=masked_previous,
            )
        )
        records.append(
            {
                "name": item["name"],
                "previousValue": None if created else previous,
                "value": item["value"],
                "orderNo": item["orderNo"],
                "created": created,
                "secret": secret,
            }
        )

    if records:
        record_variable_writes(authority.run, records)
    await session.commit()
    return {"results": results}


def _normalize_names(names: list[str]) -> list[str]:
    if len(names) > MAX_NAMES:
        raise ErrBadRequest()
    normalized: list[str] = []
    for name in names:
        value = str(name or "").strip()
        if not value or len(value) > MAX_NAME_LENGTH:
            raise ErrBadRequest()
        normalized.append(value)
    return list(dict.fromkeys(normalized))


def _normalize_write_items(items: list[Any]) -> list[dict[str, Any]]:
    if len(items) > MAX_WRITE_ITEMS:
        raise ErrBadRequest()
    normalized: list[dict[str, Any]] = []
    for item in items:
        try:
            name = validate_variable_name(item.name)
        except ValueError as exc:
            raise ErrBadRequest() from exc
        if item.order_no is not None and item.order_no <= 0:
            raise ErrBadRequest()
        normalized.append({"name": name, "value": item.value, "orderNo": item.order_no})
    return normalized


async def _authorized_task(session: AsyncSession, run_id: str, body: Any) -> WorkerTask:
    task = await session.scalar(
        select(WorkerTask).where(
            WorkerTask.domain == "ui",
            WorkerTask.task_id == body.task_id,
        )
    )
    if task is None or task.run_id != run_id:
        raise ErrNotFound()
    ensure_worker_match(task, body.worker_id)
    return task


async def _run_environment(session: AsyncSession, run: Any) -> ApiEnvironment:
    environment_id = str(getattr(run, "environment_id", "") or "")
    if not environment_id:
        raise ErrBadRequest()
    environment = await session.scalar(
        select(ApiEnvironment).where(ApiEnvironment.environment_id == environment_id)
    )
    if environment is None or environment.kind != "ui":
        raise ErrBadRequest()
    return environment

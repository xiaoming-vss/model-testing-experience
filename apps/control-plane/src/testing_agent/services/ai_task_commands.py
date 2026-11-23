from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

from testing_agent.core.enums import RUN_ACTIVE_STATUSES
from testing_agent.core.errors import (
    ErrAiGenerateTaskRunRunning,
    ErrBadRequest,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_tasks import (
    task_type_for,
)
from testing_agent.domain.generation_chain import stage_names
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.api_interface import ApiInterfaceRepository
from testing_agent.repositories.generation_current_chain import (
    bind_current_chain,
    ensure_empty_slot,
)
from testing_agent.repositories.standalone_execution import lock_or_create_stage
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_output import (
    dump_task,
)
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.resource_deletion import ResourceDeletion, SqlResourceDeletion


class GenerationTaskCommands:
    """Task lifecycle commands; each public mutation owns its existing commit."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        access: GenerationAccess,
        *,
        interfaces: ApiInterfaceRepository | None = None,
        deletion: ResourceDeletion | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.access = access
        self.interfaces = interfaces or ApiInterfaceRepository(repository.session)
        self.deletion = deletion or SqlResourceDeletion()
        self.id_factory = id_factory

    async def create(
        self,
        kind: str,
        project_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        task_id: str | None = None,
        initialize_candidate_chain: bool = False,
    ) -> dict:
        await self.access.ensure_project_access(user_id, project_id, action="write")
        self._reject_document_source(kind, body)
        sprint_id = str(body.get("sprintId") or body.get("sprint_id") or "")
        requirement_id = str(body.get("requirementId") or body.get("requirement_id") or "")
        requirement = None
        if kind in {"ui", "requirement_analysis", "code_risk_analysis", "repository_profile"}:
            if not requirement_id:
                raise ErrBadRequest()
            requirement = await self.repository.get_requirement(requirement_id)
            if requirement is None:
                raise ErrNotFound()
            sprint = await self.repository.get_sprint(requirement.sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound()
            sprint_id = requirement.sprint_id
        if kind == "test_report":
            if not sprint_id:
                raise ErrBadRequest()
            sprint = await self.repository.get_sprint(sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise ErrNotFound()
            existing = await self.repository.get_active_task_by_project_sprint_type(
                project_id, sprint_id, task_type_for(kind)
            )
            if existing is not None:
                raise ErrBadRequest()
        if sprint_id:
            await self.access.ensure_sprint_access(user_id, sprint_id, action="write")
        if requirement_id:
            await self.access.ensure_requirement_access(user_id, requirement_id, action="write")
        await self.access.validate_task_scope(
            SimpleNamespace(
                project_id=project_id, sprint_id=sprint_id, requirement_id=requirement_id
            )
        )
        interface_ids = await self._interface_ids(project_id, body) if kind == "api" else None
        task = AiGenerateTask(
            task_id=task_id or self.id_factory(),
            task_type=task_type_for(kind),
            name=str(
                body.get("name")
                or (
                    f"{requirement.name} analysis"
                    if kind == "requirement_analysis" and requirement is not None
                    else (
                        f"{requirement.name} 代码风险分析"
                        if kind == "code_risk_analysis" and requirement is not None
                        else (
                            f"{requirement.name} 仓库画像"
                            if kind == "repository_profile" and requirement is not None
                            else (
                                "test-report-generate-task"
                                if kind == "test_report"
                                else f"{kind}-case-generate-task"
                            )
                        )
                    )
                )
            ),
            project_id=project_id,
            sprint_id=sprint_id,
            requirement_id=requirement_id,
            creator_user_id=user_id,
            source_type=str(
                "interface_library"
                if kind == "api"
                else "repository"
                if kind == "ui"
                else requirement.document_type
                if kind in {"requirement_analysis", "code_risk_analysis", "repository_profile"}
                and requirement is not None
                else (
                    "daily_metrics"
                    if kind == "test_report"
                    else body.get("sourceType") or body.get("source_type") or "manual"
                )
            ),
            source_content=str(
                ""
                if kind in {"api", "ui"}
                else requirement.document_content
                if kind in {"requirement_analysis", "code_risk_analysis", "repository_profile"}
                and requirement is not None
                else body.get("sourceContent") or body.get("source_content") or ""
            ),
            interface_ids_json=interface_ids,
            instruction=str(body.get("instruction") or ""),
        )
        self.repository.add(task)
        if initialize_candidate_chain:
            if not requirement_id or kind not in {"requirement_analysis", "function", "api", "ui"}:
                raise ErrBadRequest()
            await self.repository.flush()
            chain = await bind_current_chain(
                self.repository.session,
                requirement_id=requirement_id,
                kind=cast(DesignKind, kind),
                task_id=task.task_id,
            )
            for stage_name in stage_names(kind):
                stage, _ = await lock_or_create_stage(
                    self.repository.session, task.task_id, stage_name
                )
                await ensure_empty_slot(
                    self.repository.session, chain_id=chain.chain_id, stage_id=stage.id
                )
        await self.repository.commit()
        await self.repository.refresh(task)
        return dump_task(task)

    async def update(
        self,
        kind: str,
        task_id: str,
        body: dict[str, Any],
        user_id: str,
        *,
        current_read: bool = False,
    ) -> dict:
        task = await self.access.owned_task(
            user_id, task_id, kind, action="write", current_read=current_read
        )
        if kind == "ui":
            requirement_key = "requirementId" if "requirementId" in body else "requirement_id"
            if requirement_key in body:
                requirement_id = str(body.get(requirement_key) or "")
                if not requirement_id:
                    raise ErrBadRequest()
                requirement = await self.repository.get_requirement(requirement_id)
                if requirement is None:
                    raise ErrNotFound()
                sprint = await self.repository.get_sprint(requirement.sprint_id)
                if sprint is None or sprint.project_id != task.project_id:
                    raise ErrNotFound()
                await self.access.ensure_requirement_access(user_id, requirement_id, action="write")
                task.requirement_id = requirement_id
                task.sprint_id = requirement.sprint_id
            field_map = {"name": "name", "instruction": "instruction"}
            task.source_type = "repository"
            task.source_content = ""
        elif kind == "api":
            self._reject_document_source(kind, body)
            field_map = {"name": "name", "instruction": "instruction"}
            if "interfaceIds" in body or "interface_ids" in body:
                task.interface_ids_json = await self._interface_ids(task.project_id, body)
        else:
            field_map = {
                "name": "name",
                "sourceType": "source_type",
                "source_type": "source_type",
                "sourceContent": "source_content",
                "source_content": "source_content",
                "instruction": "instruction",
            }
        for key, attr in field_map.items():
            if key in body:
                setattr(task, attr, body[key])
        await self.repository.commit()
        await self.repository.refresh(task)
        return dump_task(task)

    @staticmethod
    def _reject_document_source(kind: str, body: dict[str, Any]) -> None:
        if kind != "api":
            return
        if any(
            key in body for key in ("sourceType", "source_type", "sourceContent", "source_content")
        ):
            raise dynamic_error(ErrBadRequest, "API 用例生成任务不再接受 OpenAPI/Swagger 文档来源")

    async def _interface_ids(self, project_id: str, body: dict[str, Any]) -> list[str]:
        raw = body.get("interfaceIds")
        if raw is None:
            raw = body.get("interface_ids")
        if not isinstance(raw, list) or not raw:
            raise dynamic_error(ErrBadRequest, "请至少选择一个接口")
        ids = list(dict.fromkeys(str(value).strip() for value in raw if str(value).strip()))
        if not ids:
            raise dynamic_error(ErrBadRequest, "请至少选择一个接口")
        rows = await self.interfaces.list_by_ids_for_project(project_id, ids)
        found = {row.interface_id for row in rows}
        missing = [interface_id for interface_id in ids if interface_id not in found]
        if missing:
            raise dynamic_error(
                ErrBadRequest,
                f"接口不存在或不属于当前项目：{', '.join(missing)}",
            )
        return ids

    async def delete(self, kind: str, task_id: str, user_id: str) -> dict:
        task = await self.access.owned_task(user_id, task_id, kind, action="write")
        if task.requirement_id and kind in {
            "function",
            "api",
            "ui",
            "requirement_analysis",
            "code_risk_analysis",
        }:
            from sqlalchemy import select

            from testing_agent.models.ai_generate_task import AiGenerateTask
            from testing_agent.models.ai_generation_stage import AiGenerationStage

            await self.repository.session.scalar(
                select(AiGenerateTask).where(AiGenerateTask.task_id == task_id).with_for_update()
            )
            active = await self.repository.session.scalar(
                select(AiGenerationStage.id)
                .where(
                    AiGenerationStage.task_id == task_id,
                    AiGenerationStage.active_attempt_id.is_not(None),
                )
                .limit(1)
                .with_for_update()
            )
            if active:
                raise ErrAiGenerateTaskRunRunning()
        if kind in {"function", "api", "ui"} and not task.requirement_id:
            from sqlalchemy import select

            from testing_agent.models.ai_execution import AiExecution

            session = self.repository.session
            expected_scope = (
                task.project_id,
                task.sprint_id,
                task.requirement_id,
                task.order_id,
                task.task_type,
            )
            current = await self.repository.get_task_for_update(task_id)
            if (
                current is None
                or (
                    current.project_id,
                    current.sprint_id,
                    current.requirement_id,
                    current.order_id,
                    current.task_type,
                )
                != expected_scope
            ):
                raise ErrNotFound()
            await self.access.validate_task_scope(current)
            active = await session.scalar(
                select(AiExecution.execution_id)
                .where(
                    AiExecution.task_id == task_id,
                    AiExecution.workflow_status.in_(RUN_ACTIVE_STATUSES),
                )
                .limit(1)
                .with_for_update()
            )
            if active:
                raise ErrAiGenerateTaskRunRunning()
        await self.deletion.delete(self.repository.session, task)
        await self.repository.commit()
        return {}

    async def delete_run(self, kind: str, run_id: str, user_id: str) -> dict:
        if kind in {"code_risk_analysis", "test_report", "test_order_graph"}:
            from testing_agent.repositories.auxiliary_execution import detail_row
            from testing_agent.services.auxiliary_execution_delete import delete_auxiliary_execution

            row = await detail_row(self.repository.session, run_id)
            if row is not None:
                _, task, _ = row
                task_id = task.task_id
                # Discard the initial snapshot before rechecking current permissions.
                await self.repository.commit()
                authorized = await self.access.owned_task(user_id, task_id, kind, action="write")
                scope = (
                    authorized.project_id,
                    authorized.sprint_id,
                    authorized.requirement_id,
                    authorized.order_id,
                    authorized.task_type,
                )
                current = await self.repository.get_task_for_update(task_id)
                if (
                    current is None
                    or (
                        current.project_id,
                        current.sprint_id,
                        current.requirement_id,
                        current.order_id,
                        current.task_type,
                    )
                    != scope
                ):
                    raise ErrNotFound()
                await self.access.validate_task_scope(current)
                await delete_auxiliary_execution(
                    self.repository.session, task_id=current.task_id, execution_id=run_id
                )
                await self.repository.commit()
                return {}
            raise ErrNotFound()
        if kind in {"function", "api", "ui"}:
            from testing_agent.repositories.standalone_execution import workflow_task_id
            from testing_agent.services.standalone_execution_delete import (
                delete_standalone_execution,
            )

            session = self.repository.session
            task_id = await workflow_task_id(session, run_id)
            if task_id is None:
                raise ErrNotFound()
            await self.repository.commit()
            authorized = await self.access.owned_task(user_id, task_id, kind, action="write")
            standalone_scope = (
                authorized.project_id,
                authorized.sprint_id,
                authorized.requirement_id,
                authorized.order_id,
                authorized.task_type,
            )
            current = await self.repository.get_task_for_update(task_id)
            if (
                current is None
                or (
                    current.project_id,
                    current.sprint_id,
                    current.requirement_id,
                    current.order_id,
                    current.task_type,
                )
                != standalone_scope
            ):
                raise ErrNotFound()
            await self.access.validate_task_scope(current)
            await delete_standalone_execution(session, task_id=task_id, execution_id=run_id)
            await self.repository.commit()
            return {}
        raise ErrNotFound()

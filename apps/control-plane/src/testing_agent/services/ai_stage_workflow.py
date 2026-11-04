"""Checkpoint commands for independent functional and API executions."""

from collections.abc import Callable
from typing import Any

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import OwnedRun
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.revision_attachments import (
    attach_revision_attachments,
    normalize_attachment_file_ids,
)
from testing_agent.services.standalone_run import StandaloneRun
from testing_agent.services.stored_file import StoredFileService


class GenerationStageWorkflow:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
        id_factory: Callable[[], str] = new_id,
        files: StoredFileService | None = None,
        access: GenerationAccess | None = None,
    ) -> None:
        self.repository = repository
        self.owned_run = owned_run
        self.new_id = id_factory
        self.files = files
        self.access = access

    async def stage_connection(self, run: Any, body: Any, user_id: Any, previous_id: Any) -> str:
        connection_id = str(
            body.get("connectionId") or body.get("llmConnectionId") or previous_id or ""
        )
        connection = await require_personal_connection(
            self.repository.session, user_id, "llm", connection_id, run.project_id
        )
        return connection.connection_id

    async def prepare_revision_attachments(
        self, user_id: str, run: StandaloneRun, body: dict[str, Any]
    ) -> tuple[dict[str, str], ...]:
        file_ids = normalize_attachment_file_ids(body.get("attachmentFileIds"))
        if not file_ids:
            return ()
        if self.files is None:
            raise dynamic_error(ErrBadRequest, "文件存储未配置，不能附加图片")
        return await attach_revision_attachments(
            self.files,
            user_id=user_id,
            project_id=run.project_id,
            run_id=run.run_id,
            file_ids=file_ids,
        )

    async def review_api_checkpoint(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_api_stage import review_api_checkpoint

        run = await self.owned_run(user_id, run_id, "api", action="review")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await review_api_checkpoint(self, run, body, user_id)

    async def save_api_checkpoint(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_api_stage import save_api_checkpoint

        run = await self.owned_run(user_id, run_id, "api", action="write")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await save_api_checkpoint(self, run, body, user_id)

    async def revise_api_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_api_stage import revise_api_stage

        run = await self.owned_run(user_id, run_id, "api", action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await revise_api_stage(self, run, body, user_id)

    async def retry_api_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_api_stage import retry_api_stage

        run = await self.owned_run(user_id, run_id, "api", action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await retry_api_stage(self, run, body, user_id)

    async def save_stage_output(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_stage_workflow import save_function_stage

        run = await self.owned_run(user_id, run_id, "function", action="review")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await save_function_stage(self, run, body, user_id)

    async def revise_function_case_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        from testing_agent.services.standalone_stage_workflow import revise_function_stage

        run = await self.owned_run(user_id, run_id, "function", action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await revise_function_stage(self, run, body, user_id)

    async def review_stage(self, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        from testing_agent.services.standalone_stage_workflow import review_function_stage

        run = await self.owned_run(user_id, run_id, "function", action="review")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await review_function_stage(self, run, body, user_id)

    async def retry_stage(
        self, run_id: str, body: dict[str, Any] | None, user_id: str, *, kind: str = "function"
    ) -> dict:
        from testing_agent.services.standalone_stage_workflow import retry_function_stage

        if kind != "function":
            raise ErrNotFound()
        run = await self.owned_run(user_id, run_id, kind, action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await retry_function_stage(self, run, body or {}, user_id)

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        from testing_agent.services.stage_storage.relations import (
            find_leaf,
            graph_view,
            launch_graph,
        )
        from testing_agent.services.standalone_stage_workflow import generate_function_graph

        session = self.repository.session
        access = self.access
        found = await find_leaf(session, run_id) if access is not None else None
        if found is not None:
            assert access is not None
            leaf, source_task = found
            task = await access.owned_task(
                user_id,
                source_task.task_id,
                "function",
                action="execute",
                current_read=True,
            )
            snapshot = leaf.input_snapshot_json or {}
            connection = (body.get("connectionId") or body.get("llmConnectionId")) if body else None
            connection = connection or (
                snapshot.get("llmConnectionId") if isinstance(snapshot, dict) else ""
            )
            await launch_graph(session, task, leaf.id, user_id, connection or "")
            await session.commit()
            return await graph_view(session, task, leaf)
        run = await self.owned_run(user_id, run_id, "function", action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await generate_function_graph(self, run, body or {}, user_id)

    # Retired requirement-run URLs remain registered for existing clients. New
    # requirement work uses the requirement generation-chain stage endpoints.
    async def save_requirement_analysis_stage_output(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        raise ErrNotFound()

    async def review_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        raise ErrNotFound()

    async def revise_requirement_analysis_stage(
        self, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict:
        raise ErrNotFound()

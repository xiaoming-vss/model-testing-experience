"""Stage connection and relation-analysis commands for independent executions."""

from typing import Any

from testing_agent.core.errors import ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import OwnedRun
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.standalone_run import StandaloneRun


class GenerationStageWorkflow:
    def __init__(
        self,
        *,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
    ) -> None:
        self.repository = repository
        self.owned_run = owned_run
        self.new_id = new_id

    async def stage_connection(self, run: Any, body: Any, user_id: Any, previous_id: Any) -> str:
        connection_id = str(
            body.get("connectionId") or body.get("llmConnectionId") or previous_id or ""
        )
        connection = await require_personal_connection(
            self.repository.session, user_id, "llm", connection_id, run.project_id
        )
        return connection.connection_id

    async def generate_relation_analysis(
        self, run_id: str, body: dict[str, Any] | None, user_id: str
    ) -> dict:
        from testing_agent.services.standalone_stage_workflow import generate_function_graph

        run = await self.owned_run(user_id, run_id, "function", action="execute")
        if not isinstance(run, StandaloneRun):
            raise ErrNotFound()
        return await generate_function_graph(self, run, body or {}, user_id)

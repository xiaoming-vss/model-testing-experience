from __future__ import annotations

from typing import Any

from testing_agent.core.errors import (
    ErrBadRequest,
)
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_task_access import OwnedRun
from testing_agent.services.ai_task_output import (
    dump_run,
)
from testing_agent.services.standalone_run import StandaloneRun


class GenerationCandidateReview:
    """Edit or review candidate output; formal import remains a separate operation."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
    ) -> None:
        self.repository = repository
        self.owned_run = owned_run

    async def update_result(
        self, kind: str, run_id: str, result_yaml: str, user_id: str
    ) -> dict[str, Any]:
        if kind not in {"api", "function", "ui"}:
            raise ErrBadRequest()
        run = await self.owned_run(user_id, run_id, kind, action="write")
        if not isinstance(run, StandaloneRun):
            raise ErrBadRequest()
        return await self._edit_standalone(kind, run, result_yaml, user_id)

    async def review(
        self, kind: str, run_id: str, body: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        if kind not in {"api", "function", "ui"}:
            raise ErrBadRequest()
        run = await self.owned_run(user_id, run_id, kind, action="review")
        if not isinstance(run, StandaloneRun):
            raise ErrBadRequest()
        return await self._review_standalone(kind, run, body, user_id)

    async def _edit_standalone(
        self, kind: str, run: StandaloneRun, result: str, user_id: str
    ) -> dict[str, Any]:
        from typing import cast

        from testing_agent.domain.ai_execution_format import final_review_stage
        from testing_agent.schemas.requirement_design import DesignKind
        from testing_agent.services.generation_artifact_validation import (
            validate_generation_artifact,
        )
        from testing_agent.services.standalone_candidate import (
            lock_standalone_candidate,
            save_standalone_draft,
        )
        from testing_agent.services.standalone_execution import workflow_stage_names
        from testing_agent.services.standalone_execution_view import project_standalone_execution

        task = await self.repository.get_task_for_update(run.task_id)
        if task is None or run.status != "success":
            raise ErrBadRequest()
        stage = final_review_stage(
            task.task_type, workflow_stage_names(task.task_type, run.snapshot_json)
        )
        _, _, attempt = await lock_standalone_candidate(
            self.repository.session, task=task, execution_id=run.run_id, stage_name=stage
        )
        content, output_format = await validate_generation_artifact(
            self.repository, cast(DesignKind, kind), stage, result, run.snapshot_json
        )
        await save_standalone_draft(
            self.repository.session,
            task=task,
            execution_id=run.run_id,
            stage_name=stage,
            expected_attempt_id=attempt.id,
            actor_id=user_id,
            content=content,
            output_format=output_format,
        )
        await self.repository.commit()
        return dump_run(await project_standalone_execution(self.repository.session, run.run_id))

    async def _review_standalone(
        self, kind: str, run: StandaloneRun, body: dict[str, Any], user_id: str
    ) -> dict[str, Any]:
        from typing import cast

        from testing_agent.domain.ai_execution_format import final_review_stage
        from testing_agent.schemas.requirement_design import DesignKind
        from testing_agent.services.generation_artifact_validation import (
            validate_generation_artifact,
        )
        from testing_agent.services.standalone_candidate import (
            lock_standalone_candidate,
            review_standalone_candidate,
        )
        from testing_agent.services.standalone_execution import workflow_stage_names
        from testing_agent.services.standalone_execution_view import project_standalone_execution

        task = await self.repository.get_task_for_update(run.task_id)
        if task is None or run.status != "success":
            raise ErrBadRequest()
        stage = final_review_stage(
            task.task_type, workflow_stage_names(task.task_type, run.snapshot_json)
        )
        _, _, attempt = await lock_standalone_candidate(
            self.repository.session, task=task, execution_id=run.run_id, stage_name=stage
        )
        action = str(
            body.get("action") or body.get("reviewStatus") or body.get("status") or "approve"
        )
        if action in {"approved", "approve"}:
            await validate_generation_artifact(
                self.repository,
                cast(DesignKind, kind),
                stage,
                attempt.output_content or "",
                run.snapshot_json,
            )
            approved = True
        elif action in {"rejected", "reject"}:
            approved = False
        else:
            raise ErrBadRequest()
        await review_standalone_candidate(
            self.repository.session,
            task=task,
            execution_id=run.run_id,
            stage_name=stage,
            expected_attempt_id=attempt.id,
            actor_id=user_id,
            approved=approved,
            comment=str(body.get("reviewComment") or body.get("comment") or ""),
        )
        await self.repository.commit()
        return dump_run(await project_standalone_execution(self.repository.session, run.run_id))

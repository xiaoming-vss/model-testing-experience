from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from testing_agent.core.enums import ReviewStatus, RunStatus
from testing_agent.core.errors import (
    ErrAiGenerateTaskRunReviewed,
    ErrBadRequest,
)
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.services.ai_execution.writer import ExecutionWriter
from testing_agent.services.ai_task_access import OwnedRun
from testing_agent.services.ai_task_output import (
    dump_run,
    generated_function_cases,
    generated_payload,
    is_ai_run_reviewable,
    validate_function_candidate_cases,
    validate_ui_candidate_cases,
)
from testing_agent.services.api_import_payload import (
    validate_api_collection_import_payload,
)
from testing_agent.services.import_payload import parse_import_payload


class GenerationCandidateReview:
    """Edit or review candidate output; formal import remains a separate operation."""

    def __init__(
        self,
        repository: AiGenerateTaskRepository,
        owned_run: OwnedRun,
        execution_writer: ExecutionWriter,
    ) -> None:
        self.repository = repository
        self.owned_run = owned_run
        self.execution = execution_writer

    async def update_result(
        self, kind: str, run_id: str, result_yaml: str, user_id: str
    ) -> dict[str, Any]:
        if kind not in {"api", "function", "ui"}:
            raise ErrBadRequest()
        run = await self.owned_run(user_id, run_id, kind, action="write")
        if run.status != RunStatus.SUCCESS.value or run.review_status != ReviewStatus.PENDING.value:
            raise ErrBadRequest()
        if kind == "api":
            payload = parse_import_payload(result_yaml)
            await validate_api_collection_import_payload(
                self.repository, "", payload, check_existing=False
            )
        elif kind == "function":
            cases = generated_function_cases(SimpleNamespace(result_yaml=result_yaml))
            if not cases:
                raise ErrBadRequest()
            validate_function_candidate_cases(cases)
        else:
            validate_ui_candidate_cases(result_yaml)
        run.result_yaml = result_yaml
        await self.execution.save(
            self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
        )
        await self.repository.commit()
        await self.repository.refresh(run)
        return dump_run(run)

    async def review(self, kind: str, run_id: str, body: dict[str, Any], user_id: str) -> dict:
        run = await self.owned_run(user_id, run_id, kind, action="review")
        if not is_ai_run_reviewable(run.status):
            raise ErrBadRequest()
        if run.review_status != ReviewStatus.PENDING.value:
            raise ErrAiGenerateTaskRunReviewed()
        action = str(
            body.get("action") or body.get("reviewStatus") or body.get("status") or "approve"
        )
        if action == "approved":
            action = "approve"
        if action == "rejected":
            action = "reject"
        if kind in {"api", "function", "ui"}:
            if action == "approve":
                if run.status != RunStatus.SUCCESS.value:
                    raise ErrBadRequest()
                if kind == "api":
                    await validate_api_collection_import_payload(
                        self.repository, "", generated_payload(run)
                    )
                elif kind == "function":
                    cases = generated_function_cases(run)
                    if not cases:
                        raise ErrBadRequest()
                    validate_function_candidate_cases(cases)
                else:
                    validate_ui_candidate_cases(run.result_yaml)
                run.review_status = ReviewStatus.APPROVED.value
            elif action == "reject":
                run.review_status = ReviewStatus.REJECTED.value
            else:
                raise ErrBadRequest()
            run.review_comment = str(body.get("reviewComment") or body.get("comment") or "")
            run.reviewer_user_id = user_id
            run.reviewed_at = datetime.now(UTC)
            await self.execution.save(
                self.repository.session, run, intent=ExecutionIntent(actor_id=user_id)
            )
            await self.repository.commit()
            await self.repository.refresh(run)
            return dump_run(run)
        raise ErrBadRequest()

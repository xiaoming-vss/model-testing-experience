"""Retain only validated module metadata, isolated by stage attempt."""

from typing import Any

from pydantic import ValidationError

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
from testing_agent.schemas.module_generation import ModuleGenerationProgress, ModuleGenerationView


def accept_module_progress(attempt: AiGenerationAttempt, stage: str, summary: Any) -> None:
    """Apply newer complete snapshots without accepting arbitrary Worker payloads."""
    if not isinstance(summary, dict) or "moduleGeneration" not in summary:
        return
    if stage not in {"detailed_cases", "case_names"}:
        raise ErrBadRequest()
    try:
        progress = ModuleGenerationProgress.model_validate(summary["moduleGeneration"])
    except ValidationError as exc:
        raise ErrBadRequest() from exc
    if progress.stage != stage:
        raise ErrBadRequest()
    context = dict(attempt.output_context_json or {})
    previous = context.get("moduleGeneration")
    if isinstance(previous, dict):
        if progress.sequence <= previous.get("sequence", 0):
            return
        if [(row.id, row.module) for row in progress.modules] != [
            (row["id"], row["module"]) for row in previous["modules"]
        ]:
            raise ErrBadRequest()
    context["moduleGeneration"] = progress.model_dump(by_alias=True)
    attempt.output_context_json = context


def module_progress_view(attempt: AiGenerationAttempt | None) -> ModuleGenerationView | None:
    """Project the owning attempt and normalize interrupted modules at terminal states."""
    if attempt is None:
        return None
    value = (attempt.output_context_json or {}).get("moduleGeneration")
    if not isinstance(value, dict):
        return None
    try:
        view = ModuleGenerationView.model_validate({**value, "attemptId": attempt.id})
    except ValidationError:
        return None
    if attempt.status in {"failed", "error", "canceled"}:
        view.status = "canceled" if attempt.status == "canceled" else "failed"
        for module in view.modules:
            if module.status in {"queued", "running", "repairing"}:
                module.status = "canceled"
    return view

"""Extract the frozen source from a stage attempt."""

from typing import Any

from testing_agent.models.ai_generation_attempt import AiGenerationAttempt


def attempt_source(attempt: AiGenerationAttempt | None) -> dict[str, Any]:
    if attempt is None:
        return {}
    snapshot = attempt.input_snapshot_json or {}
    source = snapshot.get("source") if isinstance(snapshot, dict) else None
    return source if isinstance(source, dict) else {}

"""Explicit metadata for one AI execution write; never stored on an ORM instance."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class StageReview:
    stage: str
    status: Literal["approved", "rejected"]
    comment: str


@dataclass(frozen=True)
class ExecutionIntent:
    actor_id: str | None = None
    operation: Literal["generate", "revise", "retry", "edit"] | None = None
    review: StageReview | None = None
    worker_event_id: str | None = None
    reset_requirement_review: bool = False

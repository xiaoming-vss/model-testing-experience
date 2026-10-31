"""Explicit metadata for one AI execution write; never stored on an ORM instance."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class StageReview:
    stage: str
    status: Literal["approved", "rejected"]
    comment: str


@dataclass(frozen=True)
class ExecutionIntent:
    actor_id: str | None = None
    llm_connection_id: str | None = None
    operation: Literal["generate", "revise", "retry", "edit"] | None = None
    review: StageReview | None = None
    worker_event_id: str | None = None
    reset_requirement_review: bool = False
    # 本次修订尝试随指令提交的图片；只进入尝试快照，不进入运行产物。
    revision_attachments: tuple[dict[str, str], ...] = ()
    # 显式阶段运行输入，与队列及尝试在同一事务冻结；None 保留旧入口构造行为。
    input_snapshot: dict[str, Any] | None = None

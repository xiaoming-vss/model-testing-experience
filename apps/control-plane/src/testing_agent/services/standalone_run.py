"""In-memory wire data for an independent multi-stage execution."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StandaloneRun:
    """Mutable response/command data; persistence belongs to execution and attempts."""

    run_id: str
    task_id: str
    trigger_user_id: str
    status: str
    checkpoint_enabled: bool
    current_stage: str
    snapshot_json: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    history_updated_at: datetime | None = None
    project_id: str = ""
    sprint_id: str = ""
    requirement_id: str = ""
    trigger_type: str = "manual"
    stage_status: str = ""
    error_message: str = ""
    config_json: dict[str, Any] = field(default_factory=dict)
    result_yaml: str = ""
    result_summary_json: dict[str, Any] = field(default_factory=dict)
    review_status: str = "pending"
    import_status: str = "pending"
    imported_targets: list[dict[str, Any]] = field(default_factory=list)
    imported_at: datetime | None = None
    reviewer_user_id: str = ""
    reviewed_at: datetime | None = None
    review_comment: str = ""
    duration_ms: int = 0

"""Legacy wire attributes, backed by normalized stage/attempt/import records.

These are deliberately not mapped database columns. Repositories hydrate the
view before returning a run and persist changes through the lifecycle module.
"""

from copy import deepcopy
from typing import Any


def view_field(name, default):
    def get(self):
        view = self.__dict__.setdefault("_run_view", {})
        if name not in view:
            view[name] = deepcopy(default)
        return view[name]

    def set_(self, value):
        self.__dict__.setdefault("_run_view", {})[name] = value

    return property(get, set_)


class AiRunView:
    __allow_unmapped__ = True
    _actor: str | None = None
    _operation: str | None = None
    _stage_review: tuple[str, str, str] | None = None
    _worker_event: str | None = None
    _execution_state: dict[str, Any] | None = None

    project_id = view_field("project_id", "")
    sprint_id = view_field("sprint_id", "")
    requirement_id = view_field("requirement_id", "")
    trigger_type = view_field("trigger_type", "manual")
    stage_status = view_field("stage_status", "")
    error_message = view_field("error_message", "")
    remediation = view_field("remediation", "")
    config_json = view_field("config_json", {})
    result_yaml = view_field("result_yaml", "")
    result_summary_json = view_field("result_summary_json", {})
    review_status = view_field("review_status", "pending")
    import_status = view_field("import_status", "pending")
    imported_targets = view_field("imported_targets", [])
    imported_at = view_field("imported_at", None)
    import_migration_complete = view_field("import_migration_complete", True)
    reviewer_user_id = view_field("reviewer_user_id", "")
    reviewed_at = view_field("reviewed_at", None)
    review_comment = view_field("review_comment", "")
    duration_ms = view_field("duration_ms", 0)

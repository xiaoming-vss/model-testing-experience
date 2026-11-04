"""Guards shared by retired AI run URLs that remain registered for existing clients."""

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_access import OwnedRun
from testing_agent.services.project_access import ProjectAction


async def ensure_legacy_mutation_allowed(
    owned_run: OwnedRun,
    kind: DesignKind,
    run_id: str,
    user_id: str,
    *,
    action: ProjectAction = "review",
) -> None:
    run = await owned_run(user_id, run_id, kind, action=action)
    # Requirement-linked historical runs also belong to the stage chain. The
    # snapshot flag only exists on newer dispatches and cannot be the security
    # boundary: older runs would otherwise bypass versioning and conflict checks.
    if run.requirement_id or (run.snapshot_json or {}).get("generationChainManaged"):
        raise dynamic_error(ErrBadRequest, "请在需求生成链中编辑、审核或导入该阶段产物")

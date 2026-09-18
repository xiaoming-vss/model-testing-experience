"""Resolve response fields and authorize against the current owning project."""

from testing_agent.core.errors import ErrNotFound
from testing_agent.services.project_access import require_project_access


def apply_run_scope(run, context):
    run.requirement_id = context.requirement.requirement_id
    run.sprint_id = context.sprint.sprint_id
    run.project_id = context.project.project_id


async def authorize_run(repository, user_id, run):
    scope = await repository.get_run_scope(run)
    if not scope:
        raise ErrNotFound
    project = await repository.get_project(scope["project_id"])
    if project is None:
        raise ErrNotFound
    await require_project_access(repository.session, user_id, project)
    for field in ("requirement_id", "sprint_id", "project_id"):
        setattr(run, field, scope[field])
    return run

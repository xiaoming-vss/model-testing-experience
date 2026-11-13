"""Version-aware validation at worker, review, edit and import boundaries."""

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.requirement_artifacts import validate_artifact


def artifact(value, kind, *, allow_resolved_questions=False):
    try:
        return validate_artifact(value, kind, allow_resolved_questions=allow_resolved_questions)
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, str(exc)) from exc

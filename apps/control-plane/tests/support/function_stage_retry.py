"""Shared preparation for function stage retry tests; no collected cases."""

from support.function_stage_revise import RevisionRepository, revision_run


def failed_repository(stage="requirement_analysis", stage_status="failed"):
    run = revision_run(stage)
    run.status = "error"
    run.stage_status = stage_status
    run.error_message = "Unterminated string"
    run.config_json["revisionInstruction"] = "keep this round's instruction"
    repo = RevisionRepository(run)
    repo.latest.status = "error"
    return repo

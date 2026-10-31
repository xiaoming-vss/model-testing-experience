"""Approved requirement-understanding inputs for generation scenarios."""

from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask


def understanding_version(session, requirement_id="r", version_no=1, content="versioned source"):
    task_id = f"understanding-{requirement_id}"
    task = session.query(AiGenerateTask).filter_by(task_id=task_id).first()
    if task is None:
        task = AiGenerateTask(
            task_id=task_id,
            task_type="requirement_analysis",
            name="需求分析",
            project_id="p",
            sprint_id="s",
            requirement_id=requirement_id,
            creator_user_id="u",
            source_type="requirement",
            source_content="",
        )
        session.add(task)
        session.flush()
    version = AiGenerateStageVersion(
        version_id=f"understanding-{requirement_id}-v{version_no}",
        task_id=task_id,
        stage="feature_understanding",
        version_no=version_no,
        run_id=f"understanding-run-{requirement_id}",
        attempt_id=f"understanding-attempt-{requirement_id}-{version_no}",
        artifact_content=content,
        artifact_format="text",
        reviewer_user_id="u",
        upstream_versions_json={},
    )
    session.add(version)
    session.commit()
    return version

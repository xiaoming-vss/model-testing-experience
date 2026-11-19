import json

from support.ai_execution import AsyncSessionAdapter, seed_task
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.services.stage_storage import DirectStageStorage

SCOPE_ANALYSIS = {
    "schemaVersion": "1.0",
    "artifactType": "test_scope_impact_risk",
    "testObjects": [],
    "impactAreas": [],
    "risks": [],
    "openQuestions": [],
}

TRACEABLE_POINTS = {
    "schemaVersion": "1.0",
    "artifactType": "traceable_test_points",
    "reviewStatus": "independent_reviewed",
    "testPoints": [],
    "coverageGaps": [],
}
TRACEABLE_SOURCE = {"sourceContent": json.dumps({"materialBlocks": [], "questions": []})}
TRACEABLE_CONFIG = {"requirementAnalysis": SCOPE_ANALYSIS}


def setup_stage(session):
    seed_task(session)
    stage = AiGenerationStage(
        id="stage-direct", task_id="task", stage="case_names", next_version_no=1
    )
    session.add(stage)
    session.commit()
    return stage, DirectStageStorage(AsyncSessionAdapter(session))

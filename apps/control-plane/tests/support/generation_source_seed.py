"""Seed candidate source graphs for database tests."""

from support.generation_candidate_graph import SOURCE_SNAPSHOT, fixture_graph
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    RequirementGenerationChain,
)


def seed_graph(sync):
    sync.add(
        AiGenerateTask(
            task_id="material-task",
            task_type="requirement_analysis",
            name="material",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="",
        )
    )
    sync.flush()
    sync.add_all(
        [
            RequirementGenerationChain(
                chain_id="material-chain",
                requirement_id="req",
                kind="requirement_analysis",
                task_id="material-task",
            ),
            RequirementGenerationChain(
                chain_id="function-chain", requirement_id="req", kind="function", task_id="task"
            ),
            AiGenerationStage(id="stage-m", task_id="material-task", stage="extracting_text"),
            AiGenerationStage(id="stage-a", task_id="task", stage="requirement_analysis"),
            AiGenerationStage(id="stage-p", task_id="task", stage="case_names"),
        ]
    )
    sync.flush()
    graph = fixture_graph()
    for key, value in graph.items():
        sync.add(
            AiGenerationCandidate(
                candidate_id=key,
                snapshot_id=value.snapshot_id,
                chain_id="material-chain" if key == "m" else "function-chain",
                stage_id=f"stage-{key}",
                content=value.content,
                format=value.format,
                candidate_token=f"token-{key}",
                disposition="available",
                generation_mode="trial",
                created_by="u",
                source_manifest_json=value.source_manifest,
                source_snapshot_json=SOURCE_SNAPSHOT,
                content_hash=value.content_hash,
                basis_hash=value.basis_hash,
                lineage_hash=value.lineage_hash,
            )
        )
    sync.commit()
    return graph

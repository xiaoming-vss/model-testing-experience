"""Seed fully aligned imported-candidate source graphs."""

from support.generation_candidate_graph import SOURCE_SNAPSHOT, make_record
from support.generation_source_seed import seed_graph
from testing_agent.models.ai_generation_stage import AiGenerationStage
from testing_agent.models.generation_candidates import (
    AiGenerationCandidate,
    AiGenerationStageContent,
)


def seed_import_graph(sync):
    graph = seed_graph(sync)
    final = make_record(
        "d",
        "function",
        "detailed_cases",
        parents=(graph["a"], graph["p"]),
        ancestors=(graph["m"], graph["a"], graph["p"]),
    )
    sync.add(AiGenerationStage(id="stage-d", task_id="task", stage="detailed_cases"))
    sync.flush()
    sync.add(
        AiGenerationCandidate(
            candidate_id="d",
            snapshot_id=final.snapshot_id,
            chain_id="function-chain",
            stage_id="stage-d",
            content=final.content,
            format=final.format,
            candidate_token="token-d",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=final.source_manifest,
            source_snapshot_json=SOURCE_SNAPSHOT,
            content_hash=final.content_hash,
            basis_hash=final.basis_hash,
            lineage_hash=final.lineage_hash,
        )
    )
    sync.flush()
    graph["d"] = final
    for key, item in graph.items():
        candidate = sync.query(AiGenerationCandidate).filter_by(candidate_id=key).one()
        sync.add(
            AiGenerationStageContent(
                stage_id=candidate.stage_id,
                chain_id=candidate.chain_id,
                stage=item.stage,
                content=candidate.content,
                format=candidate.format,
                context_json=candidate.context_json,
                content_hash=candidate.content_hash,
                basis_hash=candidate.basis_hash,
                content_token=f"current-{key}",
                source_manifest_json=candidate.source_manifest_json,
                source_snapshot_json=candidate.source_snapshot_json,
                lineage_hash=candidate.lineage_hash,
                source_candidate_id=key,
                confirmed_by="reviewer",
                comment="accepted",
            )
        )
    sync.commit()
    return graph


def seed_api_or_ui_import_graph(sync, kind, output):
    """Make an aligned three-stage branch with server-verifiable source snapshots."""
    from testing_agent.domain.generation_content_hash import generation_content_hash
    from testing_agent.domain.generation_root_fingerprints import (
        fingerprint_generation_basis,
        fingerprint_root_input,
    )
    from testing_agent.domain.generation_source_closure import StageSnapshot, resolve_source_closure
    from testing_agent.models.ai_generate_task import AiGenerateTask
    from testing_agent.models.generation_candidates import RequirementGenerationChain
    from testing_agent.schemas.generation_candidates import (
        FrozenCandidateInput,
        FrozenCandidateSource,
        FrozenRootSource,
        FrozenSelectedSource,
    )

    task_id = f"{kind}-task"
    stages = (
        ("interface_extract", "api_design", "generate")
        if kind == "api"
        else ("ui_surface", "ui_design", "ui_yaml")
    )
    source = {"taskId": task_id, "requirementId": "req", "instruction": ""}
    if kind == "api":
        source.update(
            {
                "interfaces": [{"interfaceId": "interface", "softwareRepositoryId": "repository"}],
                "softwareRepositories": [{"softwareRepositoryId": "repository"}],
                "apiWorkflowVersion": "api_three_stage/1.0",
            }
        )
        root = fingerprint_root_input("api_interfaces", source)
    else:
        source.update(
            {
                "sourceRepository": {
                    "repositoryId": "repo",
                    "instanceUrl": "https://git.example",
                    "pathWithNamespace": "group/repo",
                    "branch": "main",
                    "commit": "abc",
                },
                "functionalCases": [{"caseId": "functional-case"}],
                "uiSourceBatchId": "batch",
                "uiWorkflowVersion": "ui_three_stage/1.0",
            }
        )
        root = fingerprint_root_input("ui_repository_cases", source)
    snapshot = {"source": source, "config": {}}
    sync.add(
        AiGenerateTask(
            task_id=task_id,
            task_type="api_case_generate" if kind == "api" else "ui_case_generate",
            name="task",
            project_id="p",
            sprint_id="s",
            requirement_id="req",
            creator_user_id="u",
            source_type="text",
            source_content="",
        )
    )
    sync.flush()
    sync.add(
        RequirementGenerationChain(
            chain_id=f"{kind}-chain", requirement_id="req", kind=kind, task_id=task_id
        )
    )
    for stage in stages:
        sync.add(AiGenerationStage(id=f"{kind}-{stage}", task_id=task_id, stage=stage))
    sync.flush()
    nodes = []
    for index, stage in enumerate(stages):
        parents = nodes if index == 2 else nodes[-1:]
        closure = resolve_source_closure(
            requirement_id="req",
            selected_snapshot_ids=tuple(item.snapshot_id for item in parents),
            required_stages=frozenset(item.key for item in parents),
            stage_snapshots=tuple(nodes),
            root_snapshots=(root,),
            current_root_hashes={root.key: root.content_hash},
            selected_root_ids=(root.snapshot_id,),
        )
        basis = fingerprint_generation_basis(
            kind=kind,
            stage=stage,
            input_snapshot=snapshot,
            roots=(root,),
            lineage_hash=closure.lineage_hash,
            attachment_hashes={},
        )
        manifest = FrozenCandidateInput(
            generation_mode="trial",
            lineage_hash=closure.lineage_hash,
            sources=[
                FrozenCandidateSource(
                    requirement_id=item.requirement_id,
                    chain_kind=item.chain_kind,
                    stage=item.stage,
                    candidate_id=item.candidate_id,
                    snapshot_id=item.snapshot_id,
                    content_hash=item.content_hash,
                    basis_hash=item.basis_hash,
                    parent_snapshot_ids=list(item.parent_snapshot_ids),
                    root_snapshot_ids=list(item.root_snapshot_ids),
                    source_batch_id=item.source_batch_id,
                )
                for item in nodes
            ],
            root_sources=[
                FrozenRootSource(
                    snapshot_id=root.snapshot_id,
                    resource_kind=root.resource_kind,
                    resource_id=root.resource_id,
                    content_hash=root.content_hash,
                    source_batch_id=root.source_batch_id,
                )
            ],
            selected_sources=[
                FrozenSelectedSource(
                    chain_kind=item.chain_kind,
                    stage=item.stage,
                    source_kind="candidate",
                    candidate_id=item.candidate_id,
                    snapshot_id=item.snapshot_id,
                )
                for item in parents
            ],
        )
        content, fmt = (output, "yaml") if index == 2 else ('{"value": 1}', "json")
        content_hash = generation_content_hash(content, fmt)
        node = StageSnapshot(
            "req",
            kind,
            stage,
            f"{kind}-candidate-{index}",
            f"{kind}-snapshot-{index}",
            content_hash,
            basis,
            tuple(item.snapshot_id for item in parents),
            (root.snapshot_id,),
            root.source_batch_id,
        )
        nodes.append(node)
        candidate = AiGenerationCandidate(
            candidate_id=node.candidate_id,
            snapshot_id=node.snapshot_id,
            chain_id=f"{kind}-chain",
            stage_id=f"{kind}-{stage}",
            content=content,
            format=fmt,
            candidate_token=f"{kind}-token-{index}",
            disposition="available",
            generation_mode="trial",
            created_by="u",
            source_manifest_json=manifest.model_dump(mode="json", by_alias=True),
            source_snapshot_json=snapshot,
            content_hash=content_hash,
            basis_hash=basis,
            lineage_hash=closure.lineage_hash,
        )
        sync.add(candidate)
        sync.flush()
        sync.add(
            AiGenerationStageContent(
                stage_id=candidate.stage_id,
                chain_id=candidate.chain_id,
                stage=stage,
                content=content,
                format=fmt,
                content_hash=content_hash,
                basis_hash=basis,
                content_token=f"{kind}-current-{index}",
                source_candidate_id=candidate.candidate_id,
                source_manifest_json=candidate.source_manifest_json,
                source_snapshot_json=snapshot,
                lineage_hash=closure.lineage_hash,
                confirmed_by="u",
            )
        )
        sync.flush()
    sync.commit()
    return root

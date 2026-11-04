"""Adapt an independent API candidate to the existing formal import operation."""

from typing import Any, Protocol

from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.standalone_import import lock_target_and_count
from testing_agent.services.ai_task_access import RequireCollectionAccess
from testing_agent.services.standalone_import_flow import import_standalone_candidate
from testing_agent.services.standalone_run import StandaloneRun


class ApiImportContext(Protocol):
    repository: AiGenerateTaskRepository
    ensure_collection_access: RequireCollectionAccess

    async def import_api_run(
        self,
        run_id: str,
        collection_id: str,
        confirm_overwrite: bool,
        user_id: str,
        *,
        artifact_content: str | None = None,
        allow_reimport: bool = False,
        approved_source: Any | None = None,
    ) -> dict[str, Any]: ...


async def import_standalone_api(
    importer: ApiImportContext,
    run: StandaloneRun,
    *,
    collection_id: str,
    confirm_overwrite: bool,
    user_id: str,
) -> dict[str, Any]:
    await importer.ensure_collection_access(user_id, collection_id, action="execute")
    await lock_target_and_count(
        importer.repository.session,
        target_type="api_collection",
        target_id=collection_id,
        project_id=run.project_id,
        changed_case_ids=(),
    )

    async def apply(source: StandaloneRun, content: str) -> dict[str, Any]:
        return await importer.import_api_run(
            run.run_id,
            collection_id,
            confirm_overwrite,
            user_id,
            artifact_content=content,
            approved_source=source,
        )

    return await import_standalone_candidate(
        importer.repository, run, task_type="api_case_generate", user_id=user_id, apply=apply
    )

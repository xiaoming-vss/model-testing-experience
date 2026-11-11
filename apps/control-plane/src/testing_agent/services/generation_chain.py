"""Requirement generation chain orchestration.

One chain is one AI task per requirement and kind. Drafts live in the existing
stage/attempt ledger; an immutable version row is written only when a stage is
approved. Chain actions never reuse another operator's model authorization.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.domain.generation_chain import (
    CHAIN_KINDS,
    CHAIN_LABELS,
    artifact_summary,
    kind_for_stage,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.schemas.generation_chain import (
    ChainImportRecordView,
    ChainImportTargetView,
    ChainStageVersionSummary,
    GenerationChainImportOptions,
    GenerationChainImportRequest,
    GenerationChainImportResponse,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.function_generate_import import import_function_run
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.stored_file import StoredFileService
from testing_agent.services.ui_generate_import import import_ui_run
from testing_agent.services.ui_generation_source import UiGenerationSourceService


def _version_label(version_no: int) -> str:
    return f"v{version_no}"


class GenerationChainService:
    def __init__(
        self,
        *,
        repository: GenerationChainRepository,
        tasks: AiGenerateTaskRepository,
        access: GenerationAccess,
        files: StoredFileService | None,
        imports: GenerationImportContext,
        api_importer: ApiCandidateImporter,
        ui_sources: UiGenerationSourceService | None = None,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.access = access
        self.files = files
        self.imports = imports
        self.api_importer = api_importer
        self.ui_sources = ui_sources
        self.new_id = id_factory

    async def scope(self, requirement_id: str, user_id: str, action: ProjectAction = "read"):
        await self.access.ensure_requirement_access(user_id, requirement_id, action=action)
        requirement = await self.tasks.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        return requirement

    async def task(
        self,
        requirement_id: str,
        kind: DesignKind,
        user_id: str,
        *,
        action: ProjectAction = "read",
        lock: bool = False,
    ) -> AiGenerateTask:
        await self.scope(requirement_id, user_id, action)
        task = (
            await self.repository.task_for_update(requirement_id, kind)
            if lock
            else await self.repository.task(requirement_id, kind)
        )
        if task is None:
            raise dynamic_error(ErrBadRequest, f"请先完成{CHAIN_LABELS[kind]}生成设置")
        if task.requirement_id != requirement_id:
            raise ErrNotFound()
        await self.access.validate_task_scope(task)
        return task

    async def optional_task(
        self, requirement_id: str, kind: DesignKind, user_id: str
    ) -> AiGenerateTask | None:
        await self.scope(requirement_id, user_id)
        task = await self.repository.task(requirement_id, kind)
        if task is not None:
            if task.requirement_id != requirement_id:
                raise ErrNotFound()
            await self.access.validate_task_scope(task)
        return task

    async def import_options(
        self,
        requirement_id: str,
        kind: DesignKind,
        version_id: str,
        user_id: str,
    ) -> GenerationChainImportOptions:
        task = await self.task(requirement_id, kind, user_id)
        row = await self._importable_version(task, kind, version_id)
        parents = await self._complete_parent_versions(task, kind, row)
        summaries = [
            self._version_summary(kind, version, imported=None) for version in parents.values()
        ]
        targets = await self._import_targets(task, kind)
        return GenerationChainImportOptions(
            kind=kind,
            version_id=row.version_id,
            version_label=_version_label(row.version_no),
            leaf_stage=row.stage,
            parent_versions={stage: version.version_id for stage, version in parents.items()},
            parents=summaries,
            targets=targets,
            target_required=kind in {"api", "ui"},
        )

    async def import_version(
        self,
        requirement_id: str,
        kind: DesignKind,
        version_id: str,
        body: GenerationChainImportRequest,
        user_id: str,
    ) -> GenerationChainImportResponse:
        task = await self.task(requirement_id, kind, user_id, action="execute", lock=True)
        row = await self._importable_version(task, kind, version_id)
        from sqlalchemy import select

        from testing_agent.models.ai_generation_attempt import AiGenerationAttempt
        from testing_agent.models.ai_generation_stage import AiGenerationStage
        from testing_agent.services.stage_storage.views import attempt_source

        attempt = await self.tasks.session.scalar(
            select(AiGenerationAttempt)
            .join(AiGenerationStage, AiGenerationStage.id == AiGenerationAttempt.stage_id)
            .where(
                AiGenerationAttempt.id == row.attempt_id,
                AiGenerationStage.task_id == task.task_id,
                AiGenerationStage.stage == row.stage,
            )
        )
        if attempt is None:
            raise ErrNotFound()
        approved_source = SimpleNamespace(
            run_id=attempt.id,
            requirement_id=task.requirement_id,
            snapshot_json=attempt_source(attempt),
            result_yaml=row.artifact_content,
            import_status="",
            imported_targets=[],
            imported_at=None,
        )
        parents = await self._complete_parent_versions(task, kind, row)
        target_id = body.target_id.strip()
        if kind in {"api", "ui"}:
            target_type = "api_collection" if kind == "api" else "ui_suite"
            if not target_id:
                raise dynamic_error(
                    ErrBadRequest,
                    "请选择要导入的"
                    + ("API 集合" if target_type == "api_collection" else "UI 测试集"),
                )
            if await self._target_row(task.requirement_id, target_type, target_id) is None:
                raise ErrNotFound()
        if kind == "function":
            result = await import_function_run(
                self.imports,
                row.attempt_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
                approved_source=approved_source,
            )
            target_type = "function_suite"
        elif kind == "api":
            result = await self.api_importer.import_api_run(
                row.attempt_id,
                target_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
                approved_source=approved_source,
            )
            target_type = "api_collection"
        else:
            result = await import_ui_run(
                self.imports,
                row.attempt_id,
                target_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
                approved_source=approved_source,
            )
            target_type = "ui_suite"
        if result.get("requiresConfirmation"):
            return GenerationChainImportResponse(
                requires_confirmation=True,
                conflicts=result.get("conflicts") or [],
                target_id=target_id,
                target_type=target_type,
            )
        changes = [
            change for change in (result.get("importChanges") or []) if isinstance(change, dict)
        ]
        if not changes:
            raise dynamic_error(ErrBadRequest, "本次导入没有可记录的正式用例变更")
        imported_at = datetime.now(UTC)
        records: list[tuple[AiGenerateVersionImport, str, str]] = []
        changed_ids: set[str] = set()
        for change in changes:
            change_target_id = str(change.get("targetId") or "")
            change_target_type = str(change.get("targetType") or "")
            if not change_target_id or change_target_type not in {
                "function_suite",
                "api_collection",
                "ui_suite",
            }:
                continue
            change_ids = sorted(
                {str(case_id) for case_id in (change.get("changedCaseIds") or []) if str(case_id)}
            )
            case_count = await self._target_case_count(change_target_type, change_target_id)
            record = AiGenerateVersionImport(
                import_id=f"vi-{self.new_id()}",
                task_id=task.task_id,
                version_id=row.version_id,
                leaf_stage=row.stage,
                target_type=change_target_type,
                target_id=change_target_id,
                parent_versions_json=(
                    {stage: version.version_id for stage, version in parents.items()}
                    if parents or row.upstream_versions_json is not None
                    else None
                ),
                changed_case_ids_json=change_ids,
                target_case_count=case_count,
                mixed_source=case_count > len(change_ids),
                reviewer_user_id=row.reviewer_user_id,
                reviewed_at=row.reviewed_at,
                review_comment=row.review_comment,
                imported_by=user_id,
                imported_at=imported_at,
                created_at=imported_at,
            )
            self.tasks.add(record)
            records.append((record, change_target_type, change_target_id))
            changed_ids.update(change_ids)
        if not records:
            raise dynamic_error(ErrBadRequest, "导入结果缺少正式目标信息")
        await self.tasks.session.flush()
        for record, change_target_type, change_target_id in records:
            target = await self._target_row(
                task.requirement_id, change_target_type, change_target_id
            )
            if target is not None:
                target.effective_import_id = record.import_id
        await self.tasks.commit()
        record_views = [
            self._import_record_view(
                record, await self.repository.version(task.task_id, record.version_id or "")
            )
            for record, _, _ in records
        ]
        from testing_agent.services.stage_storage.chain_view import build_chain_view

        chain_view = await build_chain_view(
            self.tasks.session, requirement_id, kind, task, detail=True
        )
        return GenerationChainImportResponse(
            requires_confirmation=False,
            imported=True,
            target_id=target_id if kind in {"api", "ui"} else records[0][2],
            target_type=target_type,
            changed_case_ids=sorted(changed_ids),
            changed_case_count=len(changed_ids),
            import_record=record_views[0] if record_views else None,
            import_records=record_views,
            chain=chain_view,
        )

    async def _importable_version(
        self, task: AiGenerateTask, kind: DesignKind, version_id: str
    ) -> AiGenerateStageVersion:
        if kind not in {"function", "api", "ui"}:
            raise dynamic_error(ErrBadRequest, "该生成链暂不支持导入正式资产")
        row = await self.repository.version(task.task_id, version_id)
        if row is None or row.stage not in stage_names(kind):
            raise ErrNotFound()
        if row.stage != stage_names(kind)[-1]:
            raise dynamic_error(ErrBadRequest, "只能导入链路的叶子阶段版本")
        return row

    async def _complete_parent_versions(
        self, task: AiGenerateTask, kind: DesignKind, leaf: AiGenerateStageVersion
    ) -> dict[str, AiGenerateStageVersion]:
        selected: dict[str, AiGenerateStageVersion] = {}
        visiting: set[str] = set()

        async def walk(version: AiGenerateStageVersion) -> None:
            if version.stage in visiting:
                return
            visiting.add(version.stage)
            for upstream_stage in upstream_stages(kind, version.stage):
                if kind_for_stage(upstream_stage) != kind:
                    continue  # External requirement provenance is not a formal-case parent.
                if upstream_stage in selected:
                    continue
                upstream_id = (version.upstream_versions_json or {}).get(upstream_stage)
                if not upstream_id:
                    continue
                parent = await self.repository.version(task.task_id, str(upstream_id))
                if parent is None or parent.stage != upstream_stage:
                    continue
                selected[upstream_stage] = parent
                await walk(parent)
            visiting.discard(version.stage)

        await walk(leaf)
        return selected

    async def _import_targets(
        self, task: AiGenerateTask, kind: DesignKind
    ) -> list[ChainImportTargetView]:
        if kind == "function":
            function_rows = await self.tasks.list_function_suites_by_requirement(
                task.requirement_id
            )
            targets = []
            for function_row in function_rows:
                case_count = len(await self.tasks.list_function_cases(function_row.suite_id))
                targets.append(
                    await self._import_target_view(
                        task,
                        "function_suite",
                        function_row.suite_id,
                        function_row.name,
                        case_count,
                    )
                )
            return targets
        if kind == "api":
            api_rows = await self.tasks.list_api_collections_by_requirement(task.requirement_id)
            targets = []
            for api_row in api_rows:
                case_count = len(await self.tasks.list_api_cases(api_row.collection_id))
                targets.append(
                    await self._import_target_view(
                        task, "api_collection", api_row.collection_id, api_row.name, case_count
                    )
                )
            return targets
        if kind == "ui":
            ui_rows = await self.tasks.list_ui_suites_by_requirement(task.requirement_id)
            targets = []
            for ui_row in ui_rows:
                case_count = len(await self.tasks.list_ui_cases(ui_row.suite_id))
                targets.append(
                    await self._import_target_view(
                        task, "ui_suite", ui_row.suite_id, ui_row.name, case_count
                    )
                )
            return targets
        return []

    async def _import_target_view(
        self,
        task: AiGenerateTask,
        target_type: str,
        target_id: str,
        name: str,
        case_count: int,
    ) -> ChainImportTargetView:
        target = await self._target_row(task.requirement_id, target_type, target_id)
        effective_import_id = (
            str(getattr(target, "effective_import_id", "") or "") if target else ""
        )
        effective = None
        source_deleted = False
        if effective_import_id:
            record = await self.repository.version_import(effective_import_id)
            if record is None:
                source_deleted = True
            else:
                version = (
                    await self.repository.version(task.task_id, record.version_id)
                    if record.version_id
                    else None
                )
                source_deleted = version is None and not record.attempt_id
                effective = self._import_record_view(record, version)
        return ChainImportTargetView(
            target_type=cast(Any, target_type),
            target_id=target_id,
            name=name,
            case_count=case_count,
            effective_import_id=effective_import_id,
            effective_import=effective,
            source_deleted=source_deleted,
        )

    async def _target_row(self, requirement_id: str, target_type: str, target_id: str):
        if target_type == "function_suite":
            function_target = await self.tasks.get_function_suite(target_id)
            return (
                function_target
                if function_target and function_target.requirement_id == requirement_id
                else None
            )
        if target_type == "api_collection":
            api_target = await self.tasks.get_collection(target_id)
            return (
                api_target if api_target and api_target.requirement_id == requirement_id else None
            )
        if target_type == "ui_suite":
            ui_target = await self.tasks.get_ui_suite(target_id)
            return ui_target if ui_target and ui_target.requirement_id == requirement_id else None
        return None

    async def _target_case_count(self, target_type: str, target_id: str) -> int:
        if target_type == "function_suite":
            return len(await self.tasks.list_function_cases(target_id))
        if target_type == "api_collection":
            return len(await self.tasks.list_api_cases(target_id))
        if target_type == "ui_suite":
            return len(await self.tasks.list_ui_cases(target_id))
        return 0

    def _import_record_view(
        self,
        record: AiGenerateVersionImport,
        version: AiGenerateStageVersion | None,
    ) -> ChainImportRecordView:
        changed = [str(case_id) for case_id in (record.changed_case_ids_json or []) if str(case_id)]
        return ChainImportRecordView(
            import_id=record.import_id,
            version_id=record.version_id or "",
            version_no=version.version_no if version else 0,
            version_label=_version_label(version.version_no) if version else "",
            leaf_stage=record.leaf_stage,
            parent_versions=dict(record.parent_versions_json or {}),
            changed_case_ids=changed,
            changed_case_count=len(changed),
            target_case_count=record.target_case_count,
            mixed_source=record.mixed_source,
            imported_by=record.imported_by,
            imported_at=record.imported_at,
            review_comment=record.review_comment,
        )

    async def lock_upstream_versions(self, version_ids: list[str]) -> None:
        unique_ids = sorted(set(version_ids))
        rows = await self.repository.lock_versions(unique_ids)
        if len(rows) != len(unique_ids):
            raise dynamic_error(ErrBadRequest, "选择的上游版本已删除，请重新选择")

    # --- workflow adapters -------------------------------------------------

    # --- version creation --------------------------------------------------

    # --- dispatch helpers --------------------------------------------------

    # --- projection --------------------------------------------------------

    def _version_summary(
        self,
        kind: DesignKind,
        row: AiGenerateStageVersion,
        *,
        imported: bool | None,
    ) -> ChainStageVersionSummary:
        return ChainStageVersionSummary(
            version_id=row.version_id,
            stage=row.stage,
            stage_label=stage_label(kind, row.stage),
            version_no=row.version_no,
            label=_version_label(row.version_no),
            summary=artifact_summary(row.stage, row.artifact_content, row.artifact_format),
            artifact_format=row.artifact_format,
            created_at=row.reviewed_at or row.created_at,
            reviewer_user_id=row.reviewer_user_id,
            source_run_id=row.attempt_id,
            source_batch_id=self._ui_version_batch(row) if kind == "ui" else "",
            imported=bool(imported),
        )

    @staticmethod
    def _ui_version_batch(version: AiGenerateStageVersion) -> str:
        return (version.artifact_context_json or {}).get("uiSourceBatchId") or version.attempt_id

    def validate_stage(self, kind: DesignKind, stage: str) -> None:
        if kind not in CHAIN_KINDS or stage not in stage_names(kind):
            raise ErrBadRequest()

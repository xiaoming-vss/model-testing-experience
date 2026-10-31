"""Requirement generation chain orchestration.

One chain is one AI task per requirement and kind. Drafts live in the existing
stage/attempt ledger; an immutable version row is written only when a stage is
approved. Chain actions never reuse another operator's model authorization.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.exc import IntegrityError

from testing_agent.core.enums import RUN_ACTIVE_STATUSES, ReviewStatus, RunStatus, StageStatus
from testing_agent.core.errors import ErrBadRequest, ErrNotFound, dynamic_error
from testing_agent.core.sid import new_id
from testing_agent.domain.ai_execution_intent import ExecutionIntent
from testing_agent.domain.ai_tasks import REVISION_ATTACHMENTS_FIELD, task_type_for
from testing_agent.domain.generation_chain import (
    CHAIN_KINDS,
    CHAIN_LABELS,
    STAGE_CONFIG_FIELDS,
    artifact_summary,
    artifact_value,
    first_stage,
    is_final_stage,
    kind_for_stage,
    stage_label,
    stage_names,
    upstream_stages,
)
from testing_agent.models.ai_generate_execution import (
    AiGenerateRunStage,
    AiGenerateStageAttempt,
)
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.ai_generate_version_import import AiGenerateVersionImport
from testing_agent.models.requirement import Requirement
from testing_agent.models.worker_task import WorkerTask
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.generation_chain import GenerationChainRepository
from testing_agent.schemas.generation_chain import (
    ChainImportRecordView,
    ChainImportTargetView,
    ChainLeafView,
    ChainSourceInputsView,
    ChainStageDraftView,
    ChainStageVersionSummary,
    ChainStageView,
    GenerationChainDeleteVersionResponse,
    GenerationChainImportOptions,
    GenerationChainImportRequest,
    GenerationChainImportResponse,
    GenerationChainOverview,
    GenerationChainReviewRequest,
    GenerationChainRevisionRequest,
    GenerationChainRunRequest,
    GenerationChainVersionDetail,
    GenerationChainView,
)
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_candidate_review import GenerationCandidateReview
from testing_agent.services.ai_execution.writer import ExecutionWriter
from testing_agent.services.ai_run_launcher import GenerationRunLauncher
from testing_agent.services.ai_stage_workflow import GenerationStageWorkflow
from testing_agent.services.ai_task_access import GenerationImportContext
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_generate_import import ApiCandidateImporter
from testing_agent.services.function_generate_import import import_function_run
from testing_agent.services.functional_requirement_source import functional_requirement_source
from testing_agent.services.personal_authorization import require_personal_connection
from testing_agent.services.project_access import ProjectAction
from testing_agent.services.ui_generate_import import import_ui_run
from testing_agent.services.ui_generation_sources import ui_source_inputs
from testing_agent.services.ui_generation_workflow import UiGenerationWorkflow

DISCARDED_CANDIDATE_REASON = "审核未通过，候选产物已丢弃"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _version_label(version_no: int) -> str:
    return f"v{version_no}"


def _config_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _source_inputs_view(source: dict[str, Any] | None) -> ChainSourceInputsView | None:
    """Coerce stored UI provenance into the response model declared by the schema."""
    return ChainSourceInputsView.model_validate(source) if source is not None else None


class GenerationChainService:
    def __init__(
        self,
        *,
        repository: GenerationChainRepository,
        tasks: AiGenerateTaskRepository,
        access: GenerationAccess,
        launcher: GenerationRunLauncher,
        stages: GenerationStageWorkflow,
        ui_stages: UiGenerationWorkflow,
        review: GenerationCandidateReview,
        execution: ExecutionWriter,
        imports: GenerationImportContext,
        api_importer: ApiCandidateImporter,
        id_factory: Callable[[], str] = new_id,
    ) -> None:
        self.repository = repository
        self.tasks = tasks
        self.access = access
        self.launcher = launcher
        self.stages = stages
        self.ui_stages = ui_stages
        self.review_service = review
        self.execution = execution
        self.imports = imports
        self.api_importer = api_importer
        self.new_id = id_factory

    async def _scope(self, requirement_id: str, user_id: str, action: ProjectAction = "read"):
        await self.access.ensure_requirement_access(user_id, requirement_id, action=action)
        requirement = await self.tasks.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound()
        return requirement

    async def _task(
        self,
        requirement_id: str,
        kind: DesignKind,
        user_id: str,
        *,
        action: ProjectAction = "read",
        lock: bool = False,
    ) -> AiGenerateTask:
        await self._scope(requirement_id, user_id, action)
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

    async def _optional_task(
        self, requirement_id: str, kind: DesignKind, user_id: str
    ) -> AiGenerateTask | None:
        await self._scope(requirement_id, user_id)
        task = await self.repository.task(requirement_id, kind)
        if task is not None:
            if task.requirement_id != requirement_id:
                raise ErrNotFound()
            await self.access.validate_task_scope(task)
        return task

    async def overview(self, requirement_id: str, user_id: str) -> GenerationChainOverview:
        chains = []
        requirement = await self._scope(requirement_id, user_id)
        for chain_kind in CHAIN_KINDS:
            kind = cast(DesignKind, chain_kind)
            task = await self.repository.task(requirement_id, kind)
            if task is not None:
                if task.requirement_id != requirement_id:
                    raise ErrNotFound()
                await self.access.validate_task_scope(task)
            chains.append(
                await self._chain_view(
                    requirement_id, kind, task, detail=False, requirement=requirement
                )
            )
        return GenerationChainOverview(chains=chains)

    async def chain(
        self, requirement_id: str, kind: DesignKind, user_id: str
    ) -> GenerationChainView:
        task = await self._optional_task(requirement_id, kind, user_id)
        return await self._chain_view(requirement_id, kind, task, detail=True)

    async def version(
        self, requirement_id: str, kind: DesignKind, version_id: str, user_id: str
    ) -> GenerationChainVersionDetail:
        task = await self._optional_task(requirement_id, kind, user_id)
        if task is None:
            raise ErrNotFound()
        row = await self.repository.version(task.task_id, version_id)
        if row is None or row.stage not in stage_names(kind):
            raise ErrNotFound()
        upstream = {}
        summaries = []
        recorded_upstream = row.upstream_versions_json
        if recorded_upstream is None:
            # Historical approvals were migrated without parent mappings. Use
            # the same time boundary as legacy import parent resolution.
            recorded_upstream = await self._latest_upstream_versions(
                task, kind, row.stage, before=row.reviewed_at or row.created_at
            )
        for stage, upstream_id in recorded_upstream.items():
            if stage not in upstream_stages(kind, row.stage) or not upstream_id:
                continue
            upstream[stage] = upstream_id
            found = await self.repository.version(
                await self._upstream_task_id(task, stage), upstream_id
            )
            if found is not None:
                summaries.append(self._version_summary(kind, found, imported=None))
        return GenerationChainVersionDetail(
            version_id=row.version_id,
            kind=kind,
            stage=row.stage,
            stage_label=stage_label(kind, row.stage),
            version_no=row.version_no,
            label=_version_label(row.version_no),
            summary=artifact_summary(row.stage, row.artifact_content, row.artifact_format),
            artifact_format=row.artifact_format,
            content=row.artifact_content,
            based_on_old=row.based_on_old,
            reviewer_user_id=row.reviewer_user_id,
            reviewed_at=row.reviewed_at,
            review_comment=row.review_comment,
            upstream_versions=upstream,
            upstream=summaries,
            source_inputs=(
                _source_inputs_view(await self._version_source_inputs(row))
                if kind == "ui"
                else None
            ),
        )

    async def import_options(
        self,
        requirement_id: str,
        kind: DesignKind,
        version_id: str,
        user_id: str,
    ) -> GenerationChainImportOptions:
        task = await self._task(requirement_id, kind, user_id)
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
        task = await self._task(requirement_id, kind, user_id, action="execute")
        row = await self._importable_version(task, kind, version_id)
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
                row.run_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
            )
            target_type = "function_suite"
        elif kind == "api":
            result = await self.api_importer.import_api_run(
                row.run_id,
                target_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
            )
            target_type = "api_collection"
        else:
            result = await import_ui_run(
                self.imports,
                row.run_id,
                target_id,
                body.confirm_overwrite,
                user_id,
                artifact_content=row.artifact_content,
                allow_reimport=True,
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
                parent_versions_json={
                    stage: version.version_id for stage, version in parents.items()
                },
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
                record, await self.repository.version(task.task_id, record.version_id)
            )
            for record, _, _ in records
        ]
        return GenerationChainImportResponse(
            requires_confirmation=False,
            imported=True,
            target_id=target_id if kind in {"api", "ui"} else records[0][2],
            target_type=target_type,
            changed_case_ids=sorted(changed_ids),
            changed_case_count=len(changed_ids),
            import_record=record_views[0] if record_views else None,
            import_records=record_views,
            chain=await self._chain_view(requirement_id, kind, task, detail=True),
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
        expected = set(stage_names(kind)) - {leaf.stage}

        async def walk(version: AiGenerateStageVersion) -> None:
            if version.stage in visiting:
                raise dynamic_error(ErrBadRequest, "版本父链存在循环引用")
            visiting.add(version.stage)
            for upstream_stage in upstream_stages(kind, version.stage):
                if kind_for_stage(upstream_stage) != kind:
                    continue  # External requirement provenance is not a formal-case parent.
                if upstream_stage in selected:
                    continue
                upstream_id = (version.upstream_versions_json or {}).get(upstream_stage)
                if upstream_id:
                    parent = await self.repository.version(task.task_id, str(upstream_id))
                    if parent is None or parent.stage != upstream_stage:
                        raise dynamic_error(
                            ErrBadRequest,
                            "叶子版本引用的上游版本已删除，请重新生成并审核完整链路后再导入",
                        )
                else:
                    latest = await self._latest_upstream_versions(
                        task,
                        kind,
                        version.stage,
                        before=version.reviewed_at or version.created_at,
                    )
                    fallback_id = latest.get(upstream_stage)
                    parent = (
                        await self.repository.version(task.task_id, fallback_id)
                        if fallback_id
                        else None
                    )
                    if parent is None:
                        raise dynamic_error(
                            ErrBadRequest,
                            "叶子版本缺少上游版本，请重新生成并审核完整链路后再导入",
                        )
                selected[upstream_stage] = parent
                await walk(parent)
            visiting.discard(version.stage)

        await walk(leaf)
        missing = expected - selected.keys()
        if missing:
            labels = "、".join(stage_label(kind, stage) for stage in sorted(missing))
            raise dynamic_error(
                ErrBadRequest,
                f"叶子版本缺少完整父链（{labels}），请重新生成并审核后再导入",
            )
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
                version = await self.repository.version(task.task_id, record.version_id)
                source_deleted = version is None
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
            version_id=record.version_id,
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

    async def run_stage(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainRunRequest,
        user_id: str,
    ) -> GenerationChainView:
        self._validate_stage(kind, stage)
        task = await self._task(requirement_id, kind, user_id, action="execute")
        run = await self.repository.latest_run(task.task_id)
        if body.request_id:
            existing = await self.tasks.get_run(str(body.request_id))
            if existing is not None:
                if existing.task_id != task.task_id or existing.trigger_user_id != user_id:
                    raise ErrBadRequest()
                return await self._chain_view(requirement_id, kind, task, detail=True)
        if body.refresh_inputs or body.function_case_ids is not None:
            if kind != "ui" or stage != "ui_surface":
                raise dynamic_error(ErrBadRequest, "只能在元素控件清单阶段更换 UI 生成输入")
            if run is not None and not body.refresh_inputs:
                raise dynamic_error(ErrBadRequest, "更换功能用例需要重新开始 UI 生成链")
        if run is None or body.refresh_inputs:
            if stage != first_stage(kind):
                raise dynamic_error(ErrBadRequest, "请先运行链路的首个阶段")
            payload: dict[str, Any] = {
                "connectionId": body.connection_id,
                "checkpointEnabled": True,
                "instruction": body.instruction or "",
            }
            if kind == "function":
                if set(body.upstream_versions) - {"feature_understanding"}:
                    raise ErrBadRequest()
                payload["requirementUnderstandingVersionId"] = body.upstream_versions.get(
                    "feature_understanding", ""
                )
            if kind == "ui":
                # The launcher validates selection ownership and freezes the exact content.
                if body.function_case_ids is not None:
                    payload["functionCaseIds"] = body.function_case_ids
            await self.launcher.launch(
                kind,
                task.task_id,
                payload,
                user_id,
                request_id=str(body.request_id) if body.request_id else self.new_id(),
            )
            if body.refresh_inputs and run is not None:
                await self._invalidate_previous_ui_drafts(task, run.run_id)
            refreshed = await self.repository.task(requirement_id, kind)
            if refreshed is None:
                raise ErrNotFound()
            return await self._chain_view(requirement_id, kind, refreshed, detail=True)

        if body.request_id and await self._worker_by_id(str(body.request_id)):
            return await self._chain_view(requirement_id, kind, task, detail=True)
        if await self.repository.active_worker(run.run_id) or run.status in RUN_ACTIVE_STATUSES:
            raise dynamic_error(ErrBadRequest, "当前生成链正在执行，请等待完成后再试")
        await self._reject_stage_draft(run, stage)
        selected = await self._upstream_selection(task, kind, stage, body.upstream_versions)
        await require_personal_connection(
            self.tasks.session, user_id, "llm", body.connection_id, task.project_id
        )
        run = await self.repository.run_for_update(run.run_id)
        if run is None:
            raise ErrNotFound()
        stage_row = await self.repository.stage_for_update(run.run_id, stage)
        if stage_row is None:
            raise ErrBadRequest()
        config = _config_mapping(run.config_json)
        # 生成仅接收本次选中的上游，不携带其他阶段的当前候选或旧结果。
        for field in STAGE_CONFIG_FIELDS.values():
            config.pop(field, None)
        if stage_row.review_status == ReviewStatus.REJECTED.value:
            # Historical rejections predate discard markers; stamp before resetting review.
            await self._mark_candidate_discarded(stage_row)
            config.pop(STAGE_CONFIG_FIELDS.get(stage, "resultYaml"), None)
            if is_final_stage(kind, stage):
                run.result_yaml = ""
        config.pop("revisionInstruction", None)
        if kind == "function" and stage == "requirement_analysis":
            source = await functional_requirement_source(
                self.repository,
                requirement_id,
                selected["feature_understanding"].version_id
                if "feature_understanding" in selected
                else "",
            )
            run.snapshot_json = {**(run.snapshot_json or {}), **source}
        elif kind == "function" and "requirement_analysis" in selected:
            # Selecting an older analysis also selects the requirement input it used.
            parent = await self.repository.attempt(selected["requirement_analysis"].attempt_id)
            source = (selected["requirement_analysis"].artifact_context_json or {}).get(
                "functionalSource"
            ) or {}
            if not source:
                source = (parent.input_snapshot_json or {}).get("source", {}) if parent else {}
            if source.get("requirementUnderstandingVersion"):
                run.snapshot_json = {
                    **(run.snapshot_json or {}),
                    "sourceContent": source["sourceContent"],
                    "requirementUnderstandingVersion": source.get(
                        "requirementUnderstandingVersion"
                    ),
                }
            else:
                # Legacy analyses had no version provenance. New dispatches must
                # resolve an approved version rather than reuse bound enhanced text.
                run.snapshot_json = {
                    **(run.snapshot_json or {}),
                    **await functional_requirement_source(self.repository, requirement_id),
                }
        for upstream_stage in upstream_stages(kind, stage):
            if upstream_stage not in selected:
                raise dynamic_error(
                    ErrBadRequest,
                    f"请先审核通过「{stage_label(kind, upstream_stage)}」",
                )
        for upstream_stage, version in selected.items():
            if kind_for_stage(upstream_stage) != kind:
                continue
            config[STAGE_CONFIG_FIELDS[upstream_stage]] = artifact_value(
                upstream_stage, version.artifact_content, version.artifact_format
            )
        run.config_json = config
        run.result_summary_json = {
            key: value
            for key, value in (run.result_summary_json or {}).items()
            if key != "candidateReview"
        }
        run.status = RunStatus.PENDING.value
        run.current_stage = stage
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        run.remediation = ""
        run.review_status = ReviewStatus.PENDING.value
        run.reviewer_user_id = ""
        run.reviewed_at = None
        run.review_comment = ""
        stage_row.review_status = ReviewStatus.PENDING.value
        stage_row.reviewer_user_id = None
        stage_row.reviewed_at = None
        stage_row.review_comment = None
        worker = WorkerTask(
            domain="ai",
            task_id=str(body.request_id) if body.request_id else self.new_id(),
            task_type=task_type_for(kind),
            run_id=run.run_id,
            status=RunStatus.PENDING.value,
        )
        self.tasks.add(worker)
        await self.execution.save(
            self.tasks.session,
            run,
            intent=ExecutionIntent(
                actor_id=user_id,
                llm_connection_id=body.connection_id,
                operation="generate",
                input_snapshot={
                    "source": {**(run.snapshot_json or {}), "instruction": body.instruction or ""},
                    "config": config,
                    "currentOutput": "",
                    "versioning": {
                        "baseVersionId": "",
                        "upstreamVersions": {
                            name: version.version_id for name, version in selected.items()
                        },
                    },
                },
            ),
            worker=worker,
        )
        await self.tasks.commit()
        return await self._chain_view(requirement_id, kind, task, detail=True)

    async def revise_stage(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainRevisionRequest,
        user_id: str,
    ) -> GenerationChainView:
        self._validate_stage(kind, stage)
        task = await self._task(requirement_id, kind, user_id, action="execute")
        run = await self.repository.latest_run(task.task_id)
        if run is None:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可优化的产物")
        if body.request_id and await self._worker_by_id(str(body.request_id)):
            return await self._chain_view(requirement_id, kind, task, detail=True)
        if await self.repository.active_worker(run.run_id) or run.status in RUN_ACTIVE_STATUSES:
            raise dynamic_error(ErrBadRequest, "当前生成链正在执行，请等待完成后再试")
        await require_personal_connection(
            self.tasks.session, user_id, "llm", body.connection_id, task.project_id
        )
        run = await self.repository.run_for_update(run.run_id)
        if run is None:
            raise ErrNotFound()
        stage_row = await self.repository.stage_for_update(run.run_id, stage)
        if stage_row is None:
            raise ErrBadRequest()
        if stage_row.review_status == ReviewStatus.REJECTED.value:
            raise dynamic_error(ErrBadRequest, "候选产物已丢弃，请重新生成")
        attempt = await self.repository.attempt(stage_row.current_artifact_attempt_id)
        if attempt is None or not attempt.output_content:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可优化的产物")
        if attempt.invalidated_at is not None:
            raise dynamic_error(
                ErrBadRequest,
                attempt.invalidated_reason or "产物已作废，请重新生成",
            )
        # 优化沿用该产物的运行输入，不读取其他阶段当前展示的候选。
        attachments = await self.stages.prepare_revision_attachments(
            user_id, run, {"attachmentFileIds": body.attachment_file_ids}
        )
        snapshot = deepcopy(attempt.input_snapshot_json or {})
        config = _config_mapping(snapshot.get("config"))
        config.update(attempt.output_context_json or {})
        config.pop(REVISION_ATTACHMENTS_FIELD, None)
        if stage in STAGE_CONFIG_FIELDS:
            config[STAGE_CONFIG_FIELDS[stage]] = artifact_value(
                stage, attempt.output_content, attempt.output_format
            )
        config["revisionInstruction"] = body.instruction
        snapshot["config"] = config
        snapshot["currentOutput"] = attempt.output_content if is_final_stage(kind, stage) else ""
        snapshot["source"] = {
            **(snapshot.get("source") or run.snapshot_json or {}),
            "instruction": body.instruction,
        }
        snapshot["versioning"] = {
            "baseVersionId": self.attempt_versioning(attempt).get("baseVersionId") or "",
            "upstreamVersions": await self._upstream_versions_for_attempt(
                task, kind, stage, attempt
            ),
        }
        run.config_json = config
        run.status = RunStatus.PENDING.value
        run.current_stage = stage
        run.stage_status = StageStatus.PENDING.value
        run.error_message = ""
        run.remediation = ""
        run.review_status = ReviewStatus.PENDING.value
        run.reviewer_user_id = ""
        run.reviewed_at = None
        run.review_comment = ""
        stage_row.review_status = ReviewStatus.PENDING.value
        stage_row.reviewer_user_id = None
        stage_row.reviewed_at = None
        stage_row.review_comment = None
        worker = WorkerTask(
            domain="ai",
            task_id=str(body.request_id) if body.request_id else self.new_id(),
            task_type=task_type_for(kind),
            run_id=run.run_id,
            status=RunStatus.PENDING.value,
        )
        self.tasks.add(worker)
        await self.execution.save(
            self.tasks.session,
            run,
            intent=ExecutionIntent(
                actor_id=user_id,
                llm_connection_id=body.connection_id,
                operation="revise",
                revision_attachments=attachments,
                input_snapshot=snapshot,
            ),
            worker=worker,
        )
        await self.tasks.commit()
        return await self._chain_view(requirement_id, kind, task, detail=True)

    async def review_stage(
        self,
        requirement_id: str,
        kind: DesignKind,
        stage: str,
        body: GenerationChainReviewRequest,
        user_id: str,
    ) -> GenerationChainView:
        self._validate_stage(kind, stage)
        task = await self._task(requirement_id, kind, user_id, action="review")
        run = await self.repository.latest_run(task.task_id)
        if run is None:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可审核的产物")
        stage_row = await self.repository.stage(run.run_id, stage)
        if stage_row is None:
            raise ErrBadRequest()
        if stage_row.review_status == ReviewStatus.REJECTED.value:
            if body.action == "reject" and not body.continue_after:
                return await self._chain_view(requirement_id, kind, task, detail=True)
            raise dynamic_error(ErrBadRequest, "候选产物已丢弃，请重新生成")
        attempt = await self.repository.attempt(stage_row.current_artifact_attempt_id)
        if attempt is None or not attempt.output_content:
            raise dynamic_error(ErrBadRequest, "当前阶段还没有可审核的产物")
        if attempt.invalidated_at is not None:
            raise dynamic_error(
                ErrBadRequest,
                attempt.invalidated_reason or "产物已作废，请重新生成",
            )
        existing = await self.repository.version_for_attempt(task.task_id, stage, attempt.id)
        if existing is not None:
            return await self._chain_view(requirement_id, kind, task, detail=True)
        if stage_row.review_status == ReviewStatus.APPROVED.value:
            # Recover a process loss between the workflow commit and version insert.
            await self._create_version(task, kind, stage, run, attempt, user_id, body.comment)
            return await self._chain_view(requirement_id, kind, task, detail=True)
        if body.action == "reject" and body.continue_after:
            raise ErrBadRequest()

        if body.continue_after and is_final_stage(kind, stage):
            raise dynamic_error(ErrBadRequest, "最终阶段没有“审核通过并继续”")
        if body.continue_after and (
            run.status in RUN_ACTIVE_STATUSES or await self.repository.active_worker(run.run_id)
        ):
            raise dynamic_error(ErrBadRequest, "当前生成链正在执行，可单独审核此阶段")
        continuation_connection = body.connection_id or ""
        if body.continue_after:
            if not continuation_connection:
                previous_dispatch = await self.tasks.get_latest_ai_dispatch(run.run_id)
                continuation_connection = (
                    previous_dispatch.llm_connection_id if previous_dispatch else ""
                ) or ""
            await require_personal_connection(
                self.tasks.session, user_id, "llm", continuation_connection, task.project_id
            )
            next_stage = stage_names(kind)[stage_names(kind).index(stage) + 1]
            await self._reject_stage_draft(run, next_stage)
        if stage_row.active_attempt_id:
            active = await self.repository.attempt(stage_row.active_attempt_id)
            if active is not None and active.status in {"pending", "running"}:
                raise dynamic_error(ErrBadRequest, "当前阶段正在执行，请等待完成后再审核")
        if run.current_stage != stage and not (
            run.current_stage == "completed" and is_final_stage(kind, stage)
        ):
            # 审核其他阶段不改变当前调度指针、队列状态或工作输入。
            stage_row = await self.repository.stage_for_update(run.run_id, stage)
            if stage_row is None:
                raise ErrNotFound()
            stage_row.review_status = (
                ReviewStatus.APPROVED.value
                if body.action == "approve"
                else ReviewStatus.REJECTED.value
            )
            stage_row.reviewer_user_id = user_id
            stage_row.reviewed_at = datetime.now(UTC)
            stage_row.review_comment = body.comment
            if body.action == "reject":
                await self._mark_candidate_discarded(stage_row)
            await self.tasks.commit()
            if body.action == "approve":
                await self._create_version(task, kind, stage, run, attempt, user_id, body.comment)
            if body.continue_after:
                next_stage = stage_names(kind)[stage_names(kind).index(stage) + 1]
                return await self.run_stage(
                    requirement_id,
                    kind,
                    next_stage,
                    GenerationChainRunRequest(connection_id=continuation_connection),
                    user_id,
                )
            return await self._chain_view(requirement_id, kind, task, detail=True)

        if body.action == "approve":
            # The workflow owns its own short transaction. Version insertion is a
            # second transaction under the task lock; a crash in between is repaired
            # by the approved-without-version branch above.
            await self._approve(kind, stage, run, body, user_id, continue_after=False)
            await self.tasks.refresh(run)
            stage_row = await self.repository.stage(run.run_id, stage)
            if stage_row is not None:
                attempt = await self.repository.attempt(stage_row.current_artifact_attempt_id)
            if attempt is not None:
                await self._create_version(task, kind, stage, run, attempt, user_id, body.comment)
            if body.continue_after:
                next_stage = stage_names(kind)[stage_names(kind).index(stage) + 1]
                return await self.run_stage(
                    requirement_id,
                    kind,
                    next_stage,
                    GenerationChainRunRequest(connection_id=continuation_connection),
                    user_id,
                )
        else:
            await self._reject_stage(kind, stage, run, user_id, body.comment)
        return await self._chain_view(requirement_id, kind, task, detail=True)

    async def delete_version(
        self,
        requirement_id: str,
        kind: DesignKind,
        version_id: str,
        user_id: str,
    ) -> GenerationChainDeleteVersionResponse:
        task = await self._task(requirement_id, kind, user_id, action="write", lock=True)
        row = await self.repository.version(task.task_id, version_id)
        if row is None:
            raise ErrNotFound()
        await self.repository.delete_version_imports(version_id)
        await self.tasks.session.flush()
        await self.tasks.session.delete(row)
        invalidated = await self._invalidate_dependent_drafts(task, version_id)
        if kind == "requirement_analysis" and row.stage == "feature_understanding":
            function_task = await self.repository.task(requirement_id, "function")
            if function_task is not None:
                invalidated += await self._invalidate_dependent_drafts(function_task, version_id)
        await self.tasks.commit()
        return GenerationChainDeleteVersionResponse(
            version_id=version_id,
            deleted=True,
            invalidated_draft_count=invalidated,
        )

    async def _invalidate_previous_ui_drafts(
        self, task: AiGenerateTask, previous_run_id: str
    ) -> None:
        versioned = {version.attempt_id for version in await self.repository.versions(task.task_id)}
        previous_stages = await self.repository.stages(previous_run_id)
        attempts = await self.repository.attempts_by_stages([stage.id for stage in previous_stages])
        for stage_attempts in attempts.values():
            for attempt in stage_attempts:
                if attempt.id in versioned or attempt.invalidated_at:
                    continue
                attempt.invalidated_at = datetime.now(UTC)
                attempt.invalidated_reason = "生成输入已更换，请使用新一轮生成链"
        await self.tasks.commit()

    async def _invalidate_dependent_drafts(
        self, task: AiGenerateTask, deleted_version_id: str
    ) -> int:
        versioned_attempts = {
            version.attempt_id for version in await self.repository.versions(task.task_id)
        }
        invalidated = 0
        now = datetime.now(UTC)
        reason = "上游版本已删除，请重新生成该阶段"
        for attempt, _stage in await self.repository.attempts_for_task(task.task_id):
            if attempt.invalidated_at is not None or attempt.id in versioned_attempts:
                continue
            versioning = self.attempt_versioning(attempt)
            upstream = versioning.get("upstreamVersions") or {}
            if deleted_version_id not in upstream.values():
                continue
            attempt.invalidated_at = now
            attempt.invalidated_reason = reason
            if attempt.output_content and attempt.status == "success":
                invalidated += 1
        return invalidated

    # --- workflow adapters -------------------------------------------------

    async def _approve(
        self,
        kind: DesignKind,
        stage: str,
        run: AiGenerateTaskRun,
        body: GenerationChainReviewRequest,
        user_id: str,
        *,
        continue_after: bool,
    ) -> None:
        payload: dict[str, Any] = {
            "stage": stage,
            "currentStage": stage,
            "action": "approve",
            "reviewComment": body.comment,
        }
        if body.connection_id:
            payload["connectionId"] = body.connection_id
        if kind == "function" and stage in {"requirement_analysis", "case_names"}:
            await self.stages.review_stage(
                run.run_id,
                payload,
                user_id,
                continue_after=continue_after,
                retain_rejected_draft=True,
            )
        elif kind == "function":
            await self.review_service.review("function", run.run_id, payload, user_id)
        elif kind == "requirement_analysis":
            await self.stages.review_requirement_analysis_stage(
                run.run_id,
                payload,
                user_id,
                continue_after=continue_after,
                retain_rejected_draft=True,
            )
        elif kind == "ui":
            await self.ui_stages.review_output(
                run.run_id,
                payload,
                user_id,
                continue_after=continue_after,
                retain_rejected_draft=True,
            )
        else:
            await self.review_service.review("api", run.run_id, payload, user_id)

    async def _reject_stage(
        self,
        kind: DesignKind,
        stage: str,
        run: AiGenerateTaskRun,
        user_id: str,
        comment: str,
    ) -> None:
        locked_run = await self.repository.run_for_update(run.run_id)
        if locked_run is None:
            raise ErrNotFound()
        run = locked_run
        stage_row = await self.repository.stage_for_update(run.run_id, stage)
        if stage_row is None:
            raise ErrBadRequest()
        run.status = RunStatus.SUCCESS.value
        run.stage_status = StageStatus.COMPLETED.value
        run.review_comment = comment
        if is_final_stage(kind, stage):
            run.review_status = ReviewStatus.REJECTED.value
            run.reviewer_user_id = user_id
            run.reviewed_at = datetime.now(UTC)
        from testing_agent.domain.ai_execution_intent import StageReview

        await self.execution.save(
            self.tasks.session,
            run,
            intent=ExecutionIntent(
                actor_id=user_id,
                review=StageReview(stage, ReviewStatus.REJECTED.value, comment),
            ),
        )
        await self._mark_candidate_discarded(stage_row)
        await self.tasks.commit()

    async def _mark_candidate_discarded(self, stage: AiGenerateRunStage) -> None:
        attempt = await self.repository.attempt(stage.current_artifact_attempt_id)
        if attempt is None:
            return
        attempt.invalidated_at = stage.reviewed_at or datetime.now(UTC)
        attempt.invalidated_reason = DISCARDED_CANDIDATE_REASON
        attempt.progress_json = {
            **(attempt.progress_json or {}),
            "candidateReview": {
                "status": "rejected",
                "reviewerUserId": stage.reviewer_user_id or "",
                "reviewedAt": (stage.reviewed_at or datetime.now(UTC)).isoformat(),
                "comment": stage.review_comment or "",
            },
        }

    # --- version creation --------------------------------------------------

    async def _create_version(
        self,
        task: AiGenerateTask,
        kind: DesignKind,
        stage: str,
        run: AiGenerateTaskRun,
        attempt: AiGenerateStageAttempt,
        user_id: str,
        comment: str,
    ) -> AiGenerateStageVersion | None:
        locked = await self.tasks.get_task_for_update(task.task_id)
        if locked is None:
            raise ErrNotFound()
        existing = await self.repository.version_for_attempt(task.task_id, stage, attempt.id)
        if existing is not None:
            return existing
        upstream = await self._upstream_versions_for_attempt(task, kind, stage, attempt)
        latest = await self._latest_upstream_versions(task, kind, stage)
        based_on_old = any(
            upstream.get(upstream_stage)
            and latest.get(upstream_stage)
            and upstream[upstream_stage] != latest[upstream_stage]
            for upstream_stage in upstream
        )
        version = AiGenerateStageVersion(
            version_id=f"sv-{self.new_id()}",
            task_id=task.task_id,
            stage=stage,
            version_no=await self.repository.next_version_no(task.task_id, stage),
            run_id=run.run_id,
            attempt_id=attempt.id,
            artifact_content=attempt.output_content or "",
            artifact_format=attempt.output_format or "text",
            artifact_context_json={
                **(attempt.output_context_json or {}),
                **(
                    {
                        "uiSourceInputs": ui_source_inputs(
                            (attempt.input_snapshot_json or {}).get("source") or run.snapshot_json
                        )
                    }
                    if kind == "ui"
                    else {}
                ),
                **(
                    {
                        "functionalSource": {
                            key: value
                            for key, value in (
                                (attempt.input_snapshot_json or {}).get("source")
                                or run.snapshot_json
                                or {}
                            ).items()
                            if key in {"sourceContent", "requirementUnderstandingVersion"}
                        }
                    }
                    if kind == "function"
                    else {}
                ),
            },
            upstream_versions_json=upstream,
            based_on_old=based_on_old,
            reviewer_user_id=user_id,
            reviewed_at=datetime.now(UTC),
            review_comment=comment,
            created_at=datetime.now(UTC),
        )
        self.tasks.add(version)
        try:
            await self.tasks.commit()
        except IntegrityError:
            await self.tasks.rollback()
            return await self.repository.version_for_attempt(task.task_id, stage, attempt.id)
        return version

    async def _upstream_versions_for_attempt(
        self,
        task: AiGenerateTask,
        kind: DesignKind,
        stage: str,
        attempt: AiGenerateStageAttempt,
    ) -> dict[str, str]:
        versioning = self.attempt_versioning(attempt)
        selected = {
            name: value
            for name, value in (versioning.get("upstreamVersions") or {}).items()
            if isinstance(value, str) and value and name in upstream_stages(kind, stage)
        }
        if "upstreamVersions" in versioning:
            return selected
        if kind == "function" and stage == "requirement_analysis":
            source = (attempt.input_snapshot_json or {}).get("source") or {}
            source_version = source.get("requirementUnderstandingVersion") or {}
            return (
                {"feature_understanding": source_version["versionId"]}
                if source_version.get("versionId")
                else {}
            )
        return await self._latest_upstream_versions(task, kind, stage, before=attempt.created_at)

    async def _upstream_selection(
        self,
        task: AiGenerateTask,
        kind: DesignKind,
        stage: str,
        selected_versions: dict[str, str],
    ) -> dict[str, AiGenerateStageVersion]:
        expected = set(upstream_stages(kind, stage))
        unknown = set(selected_versions) - expected
        if unknown:
            raise ErrBadRequest()
        selected: dict[str, AiGenerateStageVersion] = {}
        current_run = await self.repository.latest_run(task.task_id) if kind == "ui" else None
        for upstream_stage in expected:
            upstream_task_id = await self._upstream_task_id(task, upstream_stage)
            version_id = selected_versions.get(upstream_stage)
            if version_id:
                version = await self.repository.version(upstream_task_id, version_id)
                if version is None or version.stage != upstream_stage:
                    raise dynamic_error(ErrBadRequest, "选择的上游版本不属于当前生成链")
                if current_run is not None and version.run_id != current_run.run_id:
                    raise dynamic_error(
                        ErrBadRequest, "输入已更换，请先基于当前输入重新生成上游阶段"
                    )
                selected[upstream_stage] = version
                continue
            versions = await self.repository.versions(upstream_task_id, upstream_stage)
            if current_run is not None:
                versions = [version for version in versions if version.run_id == current_run.run_id]
            if versions:
                selected[upstream_stage] = max(versions, key=lambda row: row.version_no)
        return selected

    async def _upstream_task_id(self, task: AiGenerateTask, stage: str) -> str:
        if stage == "feature_understanding" and task.task_type == task_type_for("function"):
            source = await self.repository.task(task.requirement_id, "requirement_analysis")
            return source.task_id if source else ""
        return task.task_id

    async def _latest_upstream_versions(
        self,
        task: AiGenerateTask,
        kind: DesignKind,
        stage: str,
        *,
        before: datetime | None = None,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for upstream_stage in upstream_stages(kind, stage):
            versions = await self.repository.versions(
                await self._upstream_task_id(task, upstream_stage), upstream_stage
            )
            if before is not None:
                cutoff = _aware(before)
                assert cutoff is not None
                versions = [
                    version
                    for version in versions
                    if (reviewed := _aware(version.reviewed_at or version.created_at)) is not None
                    and reviewed <= cutoff
                ]
            if versions:
                result[upstream_stage] = max(versions, key=lambda row: row.version_no).version_id
        return result

    @staticmethod
    def attempt_versioning(attempt: AiGenerateStageAttempt) -> dict[str, Any]:
        snapshot = attempt.input_snapshot_json or {}
        versioning = snapshot.get("versioning") if isinstance(snapshot, dict) else None
        return dict(versioning) if isinstance(versioning, dict) else {}

    # --- dispatch helpers --------------------------------------------------

    async def _unreviewed_draft(self, run: AiGenerateTaskRun, row: AiGenerateRunStage) -> bool:
        attempt = await self.repository.attempt(row.current_artifact_attempt_id)
        if (
            attempt is None
            or not attempt.output_content
            or attempt.status != "success"
            or attempt.invalidated_at is not None
        ):
            return False
        version = await self.repository.version_for_attempt(run.task_id, row.stage, attempt.id)
        return version is None and row.review_status == ReviewStatus.PENDING.value

    async def _reject_stage_draft(self, run: AiGenerateTaskRun, stage: str) -> None:
        for row in await self.repository.stages(run.run_id):
            if row.stage == stage and await self._unreviewed_draft(run, row):
                raise dynamic_error(ErrBadRequest, "当前阶段还有待审核产物，请先审核或拒绝")

    async def _worker_by_id(self, worker_task_id: str) -> WorkerTask | None:
        from sqlalchemy import select

        return await self.tasks.session.scalar(
            select(WorkerTask).where(
                WorkerTask.domain == "ai", WorkerTask.task_id == worker_task_id
            )
        )

    # --- projection --------------------------------------------------------

    async def _chain_view(
        self,
        requirement_id: str,
        kind: DesignKind,
        task: AiGenerateTask | None,
        *,
        detail: bool,
        requirement: Requirement | None = None,
    ) -> GenerationChainView:
        if requirement is None:
            requirement = await self.tasks.get_requirement(requirement_id)
        if task is None:
            return GenerationChainView(
                kind=kind,
                label=CHAIN_LABELS[kind],
                configured=False,
                stages=[
                    ChainStageView(
                        stage=stage,
                        label=label,
                        order=order,
                        state="not_started",
                        upstream_stages=list(upstream_stages(kind, stage)),
                    )
                    for order, (stage, label) in enumerate(
                        [(stage, stage_label(kind, stage)) for stage in stage_names(kind)]
                    )
                ],
            )
        versions = await self.repository.versions(task.task_id)
        by_stage: dict[str, list[AiGenerateStageVersion]] = {
            stage: [] for stage in stage_names(kind)
        }
        for row in versions:
            if row.stage in by_stage:
                by_stage[row.stage].append(row)
        for rows in by_stage.values():
            rows.sort(key=lambda row: row.version_no)
        latest = {stage: rows[-1] for stage, rows in by_stage.items() if rows}
        run = await self.repository.latest_run(task.task_id)
        current_latest = {
            name: version
            for name, version in latest.items()
            if kind != "ui" or run is None or version.run_id == run.run_id
        }
        if kind == "function":
            external_versions = await self.repository.versions(
                await self._upstream_task_id(task, "feature_understanding"), "feature_understanding"
            )
            if external_versions:
                current_latest["feature_understanding"] = max(
                    external_versions, key=lambda version: version.version_no
                )
        version_imports = await self.repository.version_imports(task.task_id)
        imported_versions = {row.version_id for row in version_imports}
        stage_rows: dict[str, AiGenerateRunStage] = {}
        attempts: dict[str, list[AiGenerateStageAttempt]] = {}
        if run is not None:
            run_stages = await self.repository.stages(run.run_id)
            by_stage_id = await self.repository.attempts_by_stages([row.id for row in run_stages])
            for run_stage in run_stages:
                stage_rows[run_stage.stage] = run_stage
                attempts[run_stage.stage] = by_stage_id[run_stage.id]
        draft_count = 0
        views: list[ChainStageView] = []
        active_stage = (run.current_stage or first_stage(kind)) if run is not None else ""
        for order, stage in enumerate(stage_names(kind)):
            stage_row = stage_rows.get(stage)
            stage_attempts = attempts.get(stage, [])
            latest_attempt = max(stage_attempts, key=lambda item: item.attempt_no, default=None)
            latest_version = latest.get(stage)
            versioned_attempts = {version.attempt_id for version in by_stage[stage]}
            draft_attempt = self._draft_attempt(stage_row, stage_attempts, versioned_attempts)
            draft = None
            state: str = "not_started"
            if latest_version is not None:
                state = "approved" if stage in current_latest else "invalid"
            if run is not None and run.status in RUN_ACTIVE_STATUSES and active_stage == stage:
                state = "running"
            if latest_attempt is not None and latest_attempt.status in {"failed", "error"}:
                if latest_version is None:
                    state = "failed"
            if draft_attempt is not None:
                draft = self._draft_view(
                    kind,
                    stage,
                    run,
                    stage_row,
                    draft_attempt,
                    latest_version,
                    by_stage[stage],
                    detail=detail,
                )
                if draft.invalidated:
                    if latest_version is None and state != "running":
                        state = "invalid"
                else:
                    draft_count += 1
                    if state != "running":
                        state = "draft"
            if (
                latest_attempt is not None
                and latest_attempt.status in {"failed", "error"}
                and latest_attempt.id != (draft_attempt.id if draft_attempt else "")
            ):
                state = "failed"
            imported = bool(latest_version and latest_version.version_id in imported_versions)
            version_summaries = [
                self._version_summary(
                    kind, version, imported=version.version_id in imported_versions
                )
                for version in reversed(by_stage[stage])
            ]
            if imported and stage == stage_names(kind)[-1] and stage in current_latest:
                state = "imported"
            blocked = ""
            if upstream_stages(kind, stage):
                for upstream_stage in upstream_stages(kind, stage):
                    if upstream_stage not in current_latest:
                        blocked = f"请先审核通过「{stage_label(kind, upstream_stage)}」"
                        break
            views.append(
                ChainStageView(
                    stage=stage,
                    label=stage_label(kind, stage),
                    order=order,
                    state=state,  # type: ignore[arg-type]
                    latest_version=version_summaries[0] if version_summaries else None,
                    draft=draft,
                    versions=version_summaries,
                    upstream_stages=list(upstream_stages(kind, stage)),
                    blocked_reason=blocked,
                    error_message=(latest_attempt.error_message or "")
                    if latest_attempt and latest_attempt.status in {"failed", "error"}
                    else "",
                    active_run_id=run.run_id
                    if run is not None
                    and run.status in RUN_ACTIVE_STATUSES
                    and active_stage == stage
                    else "",
                )
            )
        leaf_stage = stage_names(kind)[-1]
        leaf_version = latest.get(leaf_stage)
        leaf_imports = (
            [row for row in version_imports if row.version_id == leaf_version.version_id]
            if leaf_version
            else []
        )
        leaf_targets: list[dict[str, str]] = []
        seen_targets: set[tuple[str, str]] = set()
        for record in leaf_imports:
            key = (record.target_type, record.target_id)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            leaf_targets.append({"targetType": record.target_type, "targetId": record.target_id})
        source_changed = False
        if run is not None and requirement is not None:
            snapshot_hash = (run.snapshot_json or {}).get("documentHash")
            source_changed = bool(
                snapshot_hash
                and requirement.document_hash
                and snapshot_hash != requirement.document_hash
            )
        if kind == "ui" and run is not None:
            snapshot = run.snapshot_json or {}
            archive = await self.repository.ui_source_archive(task.task_id)
            frozen_cases = snapshot.get("functionalCases") or []
            current_cases = (
                await self.tasks.list_ui_source_cases(
                    requirement_id, [case["caseId"] for case in frozen_cases]
                )
                if frozen_cases
                else []
            )
            source_changed = bool(
                archive is None
                or archive.file_id != snapshot.get("sourceArchiveFileId")
                or current_cases != frozen_cases
            )
        updated = [
            _aware(value)
            for value in (
                run.created_at if run else None,
                *(row.reviewed_at or row.created_at for row in versions),
                *(
                    attempt.created_at
                    for stage_attempts in attempts.values()
                    for attempt in stage_attempts
                ),
            )
        ]
        return GenerationChainView(
            kind=kind,
            label=CHAIN_LABELS[kind],
            configured=True,
            task_id=task.task_id,
            run_id=run.run_id if run else "",
            active=bool(run and run.status in RUN_ACTIVE_STATUSES),
            busy=bool(run and run.status in RUN_ACTIVE_STATUSES),
            source_changed=source_changed,
            source_inputs=_source_inputs_view(ui_source_inputs(run.snapshot_json))
            if kind == "ui" and run and detail
            else None,
            updated_at=max((value for value in updated if value), default=None),
            draft_count=draft_count,
            stages=views,
            leaf=ChainLeafView(
                stage=leaf_version.stage if leaf_version else "",
                version_id=leaf_version.version_id if leaf_version else "",
                version_no=leaf_version.version_no if leaf_version else 0,
                imported=bool(leaf_imports),
                imported_targets=leaf_targets,
                imported_at=max(
                    (record.imported_at for record in leaf_imports),
                    default=None,
                ),
            ),
        )

    @staticmethod
    def _draft_attempt(
        stage_row: AiGenerateRunStage | None,
        attempts: list[AiGenerateStageAttempt],
        versioned_attempts: set[str],
    ) -> AiGenerateStageAttempt | None:
        """Only the stage's current artifact awaiting review is a draft.

        Superseded attempts stay in the attempt ledger for diagnostics; they are
        not drafts even though no version was ever created from them. An approved
        stage keeps its current artifact as a draft only while the version is
        missing, which is the recovery path after a crash or a version deletion.
        """
        if stage_row is None or stage_row.review_status not in {
            ReviewStatus.PENDING.value,
            ReviewStatus.APPROVED.value,
        }:
            return None
        attempt = next(
            (item for item in attempts if item.id == stage_row.current_artifact_attempt_id),
            None,
        )
        if (
            attempt is None
            or not attempt.output_content
            or attempt.status != "success"
            or attempt.id in versioned_attempts
            or attempt.invalidated_reason == DISCARDED_CANDIDATE_REASON
        ):
            return None
        return attempt

    def _draft_view(
        self,
        kind: DesignKind,
        stage: str,
        run: AiGenerateTaskRun | None,
        stage_row: AiGenerateRunStage | None,
        attempt: AiGenerateStageAttempt,
        latest_version: AiGenerateStageVersion | None,
        stage_versions: list[AiGenerateStageVersion],
        *,
        detail: bool,
    ) -> ChainStageDraftView:
        versioning = self.attempt_versioning(attempt)
        base_id = str(versioning.get("baseVersionId") or "")
        if not base_id and latest_version is not None:
            base_id = latest_version.version_id
        base_version = next(
            (version for version in stage_versions if version.version_id == base_id),
            latest_version,
        )
        base_label = _version_label(base_version.version_no) if base_version else ""
        status = (
            "invalidated"
            if attempt.invalidated_at is not None
            else ReviewStatus.REJECTED.value
            if stage_row is not None and stage_row.review_status == ReviewStatus.REJECTED.value
            else "draft"
        )
        return ChainStageDraftView(
            attempt_id=attempt.id,
            run_id=run.run_id if run else "",
            status=status,
            summary=artifact_summary(stage, attempt.output_content or "", attempt.output_format),
            artifact_format=attempt.output_format or "text",
            content=(attempt.output_content or "") if detail else "",
            revision=attempt.attempt_no,
            base_version_id=base_id,
            base_version_label=base_label,
            upstream_versions={
                key: value
                for key, value in (versioning.get("upstreamVersions") or {}).items()
                if isinstance(value, str)
            },
            source_inputs=_source_inputs_view(
                ui_source_inputs((attempt.input_snapshot_json or {}).get("source"))
            )
            if kind == "ui" and detail
            else None,
            instruction=attempt.revision_instruction or "",
            invalidated=attempt.invalidated_at is not None,
            invalidated_reason=attempt.invalidated_reason or "",
            created_at=attempt.created_at,
        )

    async def _version_source_inputs(
        self, version: AiGenerateStageVersion
    ) -> dict[str, Any] | None:
        context = version.artifact_context_json or {}
        if "uiSourceInputs" in context:
            return context["uiSourceInputs"]
        # Legacy versions may predate provenance copied into the immutable version row.
        attempt = await self.repository.attempt(version.attempt_id)
        if attempt is not None:
            source = ui_source_inputs((attempt.input_snapshot_json or {}).get("source"))
            if source is not None:
                return source
        run = await self.tasks.get_run(version.run_id)
        return ui_source_inputs(run.snapshot_json) if run else None

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
            based_on_old=row.based_on_old,
            source_run_id=row.run_id,
            imported=bool(imported),
        )

    def _validate_stage(self, kind: DesignKind, stage: str) -> None:
        if kind not in CHAIN_KINDS or stage not in stage_names(kind):
            raise ErrBadRequest()

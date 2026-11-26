"""Generate the advisory requirement-review report for the first chain stage."""

import json
from pathlib import Path

from testing_agent_ai_worker.core.errors import UserFacingError
from testing_agent_ai_worker.models.execution import TaskProgress
from testing_agent_ai_worker.platform.revision_attachments import (
    load_revision_images,
    revision_attachment_refs,
    revision_image_paths,
)
from testing_agent_ai_worker.requirement_artifacts import validate_artifact
from testing_agent_ai_worker.skill_names import REQUIREMENT_REVIEW_SKILL
from testing_agent_ai_worker.tasks.requirement_analysis.output import (
    build_review_config_json,
    build_review_summary,
)
from testing_agent_ai_worker.tasks.requirement_analysis.validation import generate_validated

REVIEW_INSTRUCTION = (
    "正式产物必须符合本阶段 JSON Schema，按本次产物交接说明返回。"
    "只输出需求评审报告，不生成测试用例、测试点或执行结论；"
    "blocker 必须填写 failureMode；不要编造接口、SLA、字段、状态或业务规则。"
)


def execute_review_stage(
    *,
    task,
    started_at,
    progress_callback,
    config_path,
    workspace,
    skill_runner,
    source_downloader,
    attachment_downloader=None,
):
    """Return None: the review stage stops at waiting_review, never as a final result."""
    if task.payload.metadata.get("workflowVersion", 2) != 2:
        raise UserFacingError("不支持的需求分析工作流版本")
    if not task.checkpoint_enabled:
        raise UserFacingError("需求分析必须启用人工审核")
    stage = task.current_stage or "requirement_review"
    if stage != "requirement_review":
        raise UserFacingError(f"需求评审不支持阶段: {stage}")
    config = json.loads(task.config_json or "{}")
    if not isinstance(config, dict):
        raise UserFacingError("configJson 必须是对象")
    revision = str(config.get("revisionInstruction") or "").strip()
    if source_downloader is None:
        raise ValueError("requirement_analysis source_downloader is required")
    body = {
        "workflowVersion": 2,
        "outputProfile": "json",
        "sourcePath": str(
            source_downloader.download_source(
                document_download_url=task.payload.document_download_url,
                document_type=task.payload.document_type,
                task=task,
                workspace=workspace,
            )
        ),
        "documentType": task.payload.document_type,
    }
    media = []
    if task.payload.document_type == "richtext":
        body["images"] = source_downloader.download_images(
            source=Path(body["sourcePath"]), task=task
        )
        media = [entry["sourcePath"] for entry in body["images"]]
    body["sourceName"] = task.payload.metadata.get("documentFilename") or "原始需求材料"
    file_id = task.payload.metadata.get("documentFileId")
    body["sourceLocation"] = (
        f"/v1/files/{file_id}/download"
        if file_id
        else f"/v1/requirements/{task.requirement_id}/download"
    )
    if revision:
        body["revisionInstruction"] = revision
        body["currentArtifact"] = validate_artifact(
            config.get("reviewOutput"), "requirement_review"
        )
        images = load_revision_images(
            task_id=task.task_id,
            workspace=workspace,
            config=config,
            downloader=attachment_downloader,
        )
        media.extend(revision_image_paths(images))
        body["revisionAttachments"] = revision_attachment_refs(images)
    artifact = generate_validated(
        kind="requirement_review",
        task=task,
        stage=stage,
        workspace=workspace,
        generate=skill_runner,
        report=progress_callback,
        arguments={
            **({"media": media} if media else {}),
            "input_text": json.dumps(body, ensure_ascii=False),
            "session_key": task.session_key,
            "skill_name": REQUIREMENT_REVIEW_SKILL,
            "config_path": config_path,
            "workspace": str(workspace),
            "extra_instruction": REVIEW_INSTRUCTION,
        },
    )
    progress_callback(
        TaskProgress(
            task_id=task.task_id,
            attempt_id=task.attempt_id,
            current_stage=stage,
            stage_status="waiting_review",
            intermediate_json_text=build_review_config_json(review_output=artifact),
            result_summary_json=json.dumps(build_review_summary(artifact), ensure_ascii=False),
        )
    )
    return None

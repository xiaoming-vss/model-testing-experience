"""Generate a material artifact for a single-stage requirement workflow."""

import json
from datetime import datetime
from pathlib import Path

from testing_agent_ai_worker.models.execution import TaskResult, TaskStatus
from testing_agent_ai_worker.platform.revision_attachments import (
    parse_revision_attachments,
)
from testing_agent_ai_worker.requirement_artifacts import validate_artifact
from testing_agent_ai_worker.tasks.requirement_analysis.confirmation_coverage import (
    collect_confirmation_references,
)
from testing_agent_ai_worker.tasks.requirement_analysis.output import (
    build_config_json,
    build_result_summary_json,
)
from testing_agent_ai_worker.tasks.requirement_analysis.validation import generate_validated

READABLE_INSTRUCTION = (
    "正式产物必须符合本阶段 JSON Schema，按本次产物交接说明返回。"
    "用户答复作为 user_confirmation 来源，仅用于明确覆盖的功能；"
    "已解决问题删除，部分解决仅保留剩余问题；未涉及的材料及答复保持不变。"
    "修订图片仅作为本轮补充依据，不得推断图片未表达的行为。"
)


def execute_material_stage(
    *,
    task,
    started_at,
    progress_callback,
    config_path,
    workspace,
    skill_runner,
    source_downloader,
    first_skill_name,
    attachment_downloader=None,
):
    if task.payload.metadata.get("workflowVersion", 2) != 2:
        raise ValueError("不支持的需求分析工作流版本")
    if not task.checkpoint_enabled:
        raise ValueError("需求分析必须启用材料人工审核")
    stage = task.current_stage or "extracting_text"
    config = json.loads(task.config_json or "{}")
    if not isinstance(config, dict):
        raise ValueError("configJson 必须是对象")
    revision = str(config.get("revisionInstruction") or "").strip()
    body = {"workflowVersion": 2, "outputProfile": "json"}
    media = []
    confirmation_references = []
    if stage == "extracting_text":
        if source_downloader is None:
            raise ValueError("requirement_analysis source_downloader is required")
        body["sourcePath"] = str(
            source_downloader.download_source(
                document_download_url=task.payload.document_download_url,
                document_type=task.payload.document_type,
                task=task,
                workspace=workspace,
            )
        )
        body["documentType"] = task.payload.document_type
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
            body["currentArtifact"] = validate_artifact(
                config.get("firstStepOutput"), "document_extraction", allow_resolved_questions=True
            )
        if "currentArtifact" in body:
            confirmation_references = collect_confirmation_references(body["currentArtifact"])
        body["confirmationReferences"] = confirmation_references
        name, kind = first_skill_name, "document_extraction"
    else:
        raise ValueError(f"需求分析不支持阶段: {stage}")
    if revision:
        attachments = parse_revision_attachments(config)
        if attachments:
            if attachment_downloader is None:
                raise ValueError("未配置继续优化图片下载器")
            revision_images = attachment_downloader.download(
                task_id=task.task_id, workspace=workspace, attachments=attachments
            )
            media.extend(entry["sourcePath"] for entry in revision_images)
            body["revisionAttachments"] = [
                {"fileId": entry["fileId"], "filename": entry["filename"]}
                for entry in revision_images
            ]
        body["revisionInstruction"] = revision
    artifact = generate_validated(
        kind=kind,
        task=task,
        stage=stage,
        workspace=workspace,
        generate=skill_runner,
        report=progress_callback,
        required_confirmations=confirmation_references,
        arguments={
            **({"media": media} if media else {}),
            "input_text": json.dumps(body, ensure_ascii=False),
            "session_key": task.session_key,
            "skill_name": name,
            "config_path": config_path,
            "workspace": str(workspace),
            "extra_instruction": "\n\n".join(
                part
                for part in (
                    task.payload.extra_instruction,
                    READABLE_INSTRUCTION,
                )
                if part
            ),
        },
    )
    config_json = build_config_json(first_step_output=artifact)
    final = json.dumps(artifact, ensure_ascii=False, separators=(",", ":"))
    return TaskResult(
        task_id=task.task_id,
        attempt_id=task.attempt_id,
        generate_task_id=task.generate_task_id,
        status=TaskStatus.SUCCESS,
        intermediate_json_text=config_json,
        output_yaml=final,
        result_summary_json=build_result_summary_json(
            task=task,
            status=TaskStatus.SUCCESS,
            config_json=config_json,
            output_yaml=final,
            error_message=None,
        ),
        started_at=started_at,
        finished_at=datetime.now().astimezone(),
    )

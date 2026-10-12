"""The version-2 requirement workflow: extraction review, then understanding."""

import json
from datetime import datetime
from pathlib import Path

from testing_agent_ai_worker.models.execution import TaskProgress, TaskResult, TaskStatus
from testing_agent_ai_worker.requirement_artifacts import validate_artifact
from testing_agent_ai_worker.tasks.requirement_analysis.output import (
    build_config_json,
    build_result_summary_json,
)
from testing_agent_ai_worker.tasks.requirement_analysis.validation import generate_validated

JSON_INSTRUCTION = (
    "workflowVersion=2，outputProfile=json。只返回符合本阶段 schema 的完整 JSON 对象。"
    "明确答复必须补入对应事实、操作、规则或交互，并更新确认状态和来源；"
    "已解决问题从 questions 删除，清理所有 relatedQuestionIds；不能只删问题而保留对应未知内容。"
    "questions 仅保留 status=open 的剩余缺口，全部解决时为 []；修订不自动关闭未答复问题。"
)


def execute_two_stage(
    *,
    task,
    started_at,
    progress_callback,
    config_path,
    workspace,
    skill_runner,
    source_downloader,
    first_skill_name,
    second_skill_name,
):
    if task.payload.metadata.get("workflowVersion", 2) != 2:
        raise ValueError("不支持的需求分析工作流版本")
    if not task.checkpoint_enabled:
        raise ValueError("两阶段需求分析必须启用第一阶段人工检查点")
    stage = task.current_stage or "extracting_text"
    config = json.loads(task.config_json or "{}")
    if not isinstance(config, dict):
        raise ValueError("configJson 必须是对象")
    revision = str(config.get("revisionInstruction") or "").strip()
    body = {"workflowVersion": 2, "outputProfile": "json"}
    media = []
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
        name, kind = first_skill_name, "document_extraction"
    elif stage == "feature_understanding":
        first = validate_artifact(
            config.get("firstStepOutput"), "document_extraction", allow_resolved_questions=True
        )
        body["documentExtraction"] = first
        # Kept explicit on fresh sessions, retries and revisions.
        body["originalSourceContent"] = task.payload.source_content
        if body["originalSourceContent"].startswith(("/internal/", "/v1/", "http://", "https://")):
            body["originalSourceContent"] = ""
        if revision:
            body["currentArtifact"] = validate_artifact(
                config.get("resultYaml") or config.get("finalOutput"),
                "requirement_understanding",
                allow_resolved_questions=True,
            )
        name, kind = second_skill_name, "requirement_understanding"
    else:
        raise ValueError(f"两阶段需求分析不支持阶段: {stage}")
    if revision:
        body["revisionInstruction"] = revision
    artifact = generate_validated(
        kind=kind,
        task=task,
        stage=stage,
        workspace=workspace,
        generate=skill_runner,
        report=progress_callback,
        arguments={
            **({"media": media} if media else {}),
            "input_text": json.dumps(body, ensure_ascii=False),
            "session_key": task.nanobot_session_key,
            "skill_name": name,
            "config_path": config_path,
            "workspace": str(workspace),
            "extra_instruction": "\n\n".join(
                part for part in (task.payload.extra_instruction, JSON_INSTRUCTION) if part
            ),
        },
    )
    if stage == "extracting_text":
        config_json = build_config_json(first_step_output=artifact)
        progress_callback(
            TaskProgress(
                task_id=task.task_id,
                run_id=task.run_id,
                current_stage=stage,
                stage_status="waiting_review",
                intermediate_json_text=config_json,
                output_yaml="",
                result_summary_json=build_result_summary_json(
                    task=task,
                    status="waiting_review",
                    config_json=config_json,
                    output_yaml="",
                    error_message=None,
                ),
            )
        )
        return None
    config_json = build_config_json(first_step_output=first)
    final = json.dumps(artifact, ensure_ascii=False, separators=(",", ":"))
    return TaskResult(
        task_id=task.task_id,
        run_id=task.run_id,
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

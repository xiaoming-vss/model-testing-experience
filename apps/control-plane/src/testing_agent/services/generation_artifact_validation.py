"""Validate one editable generation-chain artifact before saving or approving it."""

import json
from types import SimpleNamespace

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.schemas.requirement_design import DesignKind
from testing_agent.services.ai_task_output import (
    generated_function_cases,
    validate_function_candidate_cases,
)
from testing_agent.services.api_import_payload import validate_api_collection_import_payload
from testing_agent.services.import_payload import parse_import_payload
from testing_agent.services.requirement_analysis_contracts import artifact
from testing_agent.services.ui_generation_contracts import validate_ui_output


async def validate_generation_artifact(
    repository: AiGenerateTaskRepository,
    kind: DesignKind,
    stage: str,
    content: str,
    source_snapshot: dict,
) -> tuple[str, str]:
    """Return validated content and format without consulting mutable current inputs."""
    if not content.strip():
        raise dynamic_error(ErrBadRequest, "阶段产物不能为空")
    if kind == "requirement_analysis":
        artifact_kind = {
            "extracting_text": "document_extraction",
            "feature_understanding": "requirement_understanding",
        }.get(stage)
        if artifact_kind is None:
            raise ErrBadRequest()
        value = artifact(content, artifact_kind)
        return json.dumps(value, ensure_ascii=False), "json"
    if kind == "ui":
        run = SimpleNamespace(snapshot_json=source_snapshot)
        value = validate_ui_output(run, stage, content)
        if stage == "ui_yaml":
            return str(value), "yaml"
        return json.dumps(value, ensure_ascii=False), "json"
    if (kind, stage) in {
        ("function", "requirement_analysis"),
        ("function", "case_names"),
        ("api", "openapi_extract"),
    }:
        try:
            value = json.loads(content)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是合法 JSON") from exc
        if not isinstance(value, dict) or not value:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是非空 JSON 对象")
        return json.dumps(value, ensure_ascii=False), "json"
    if kind == "function" and stage == "detailed_cases":
        cases = generated_function_cases(SimpleNamespace(result_yaml=content))
        if not cases:
            raise ErrBadRequest()
        validate_function_candidate_cases(cases)
        return content, "yaml"
    if kind == "api" and stage == "generate":
        payload = parse_import_payload(content)
        await validate_api_collection_import_payload(repository, "", payload, check_existing=False)
        return content, "yaml"
    raise ErrBadRequest()

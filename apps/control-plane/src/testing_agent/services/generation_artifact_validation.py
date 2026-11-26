"""Validate one editable generation-chain artifact before saving or approving it."""

import json
from types import SimpleNamespace
from typing import Any

from testing_agent.core.errors import ErrBadRequest, dynamic_error
from testing_agent.domain.generation_chain import (
    HISTORICAL_REQUIREMENT_STAGE,
    HISTORICAL_TEST_STAGE,
)
from testing_agent.domain.historical_requirement_artifacts import validate_historical_output
from testing_agent.domain.historical_test_case_artifacts import validate_verification_run_output
from testing_agent.domain.test_scope_analysis import validate_test_scope
from testing_agent.domain.traceable_test_points import validate_traceable_test_points
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


def _json_object(value: object) -> dict | None:
    """Parse a frozen artifact, treating non-JSON text as unavailable upstream input."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _strict_json_object(content: str) -> dict[str, Any]:
    """复平面只做浅层严格解析：拒绝重复键、NaN 与 Infinity。"""

    def unique_pairs(pairs: list[tuple[Any, Any]]) -> dict:
        result: dict[Any, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复字段: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError(f"非法 JSON 数值: {value}")

    try:
        value = json.loads(content, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    except ValueError as exc:
        raise dynamic_error(ErrBadRequest, "阶段产物必须是合法 JSON") from exc
    if not isinstance(value, dict) or not value:
        raise dynamic_error(ErrBadRequest, "阶段产物必须是非空 JSON 对象")
    return value


def _validate_api_design_shallow(value: dict[str, Any], extraction: Any) -> None:
    """控制面只校验设计产物的结构和接口归属；覆盖规则由 Worker 完整校验。"""

    if value.get("schemaVersion") != "api_test_design/1.0":
        raise dynamic_error(ErrBadRequest, "设计产物 schemaVersion 必须是 api_test_design/1.0")
    interfaces = value.get("interfaces")
    if not isinstance(interfaces, dict) or not interfaces:
        raise dynamic_error(ErrBadRequest, "设计产物必须包含非空 interfaces 对象")
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for name, item in interfaces.items():
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            raise dynamic_error(ErrBadRequest, "设计产物接口项必须是对象")
        method, path = item.get("method"), item.get("path")
        cases = item.get("cases")
        if not isinstance(method, str) or not method or not isinstance(path, str) or not path:
            raise dynamic_error(ErrBadRequest, f"设计产物接口 {name} 缺少 method/path")
        if not isinstance(cases, list) or not cases:
            raise dynamic_error(ErrBadRequest, f"设计产物接口 {name} 的 cases 不能为空")
        for case in cases:
            if not isinstance(case, dict):
                raise dynamic_error(ErrBadRequest, f"设计产物接口 {name} 的用例必须是对象")
            case_id, title = case.get("id"), case.get("title")
            if (
                not isinstance(case_id, str)
                or not case_id
                or not isinstance(title, str)
                or not title
            ):
                raise dynamic_error(ErrBadRequest, f"设计产物接口 {name} 的用例缺少 id/title")
            if case_id in seen_ids or title.casefold() in seen_titles:
                raise dynamic_error(ErrBadRequest, "设计产物用例 id/title 必须全局唯一")
            seen_ids.add(case_id)
            seen_titles.add(title.casefold())
            if not isinstance(case.get("basis"), dict) or not isinstance(
                case.get("expected"), dict
            ):
                raise dynamic_error(ErrBadRequest, "设计产物用例必须包含 basis 和 expected")
            expected = case["expected"]
            if expected.get("statusClass") not in {"2xx", "4xx"}:
                raise dynamic_error(ErrBadRequest, "设计产物 statusClass 必须是 2xx 或 4xx")
    if isinstance(extraction, dict):
        if set(interfaces) != set(extraction):
            raise dynamic_error(ErrBadRequest, "设计产物接口集合必须与提取产物完全一致")
        for name, item in interfaces.items():
            baseline = extraction[name]
            if not isinstance(baseline, dict) or (
                item.get("method") != baseline.get("method")
                or item.get("path") != baseline.get("path")
            ):
                raise dynamic_error(
                    ErrBadRequest, f"设计产物接口 {name} 的 method/path 与提取产物不一致"
                )


def _frozen_inputs(source_snapshot: dict) -> tuple[dict, dict]:
    """Accept either a full input snapshot or its already-unwrapped source dict."""
    if not isinstance(source_snapshot, dict):
        return {}, {}
    source = source_snapshot.get("source")
    if isinstance(source, dict):
        config = source_snapshot.get("config")
        return source, config if isinstance(config, dict) else {}
    return source_snapshot, {}


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
    if (kind, stage) == ("requirement_analysis", HISTORICAL_TEST_STAGE):
        source, _ = _frozen_inputs(source_snapshot)
        try:
            value = validate_verification_run_output(content, source.get("sourceContent"))
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, "历史用例核验结果与冻结的规则或用例不一致") from exc
        return json.dumps(value, ensure_ascii=False), "json"
    if (kind, stage) == ("requirement_analysis", HISTORICAL_REQUIREMENT_STAGE):
        source, _ = _frozen_inputs(source_snapshot)
        try:
            value = validate_historical_output(content, source.get("sourceContent"))
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, "历史需求关联结果与本次冻结材料不一致") from exc
        return json.dumps(value, ensure_ascii=False), "json"
    if kind == "requirement_analysis":
        artifact_kind = {
            "requirement_review": "requirement_review",
            "extracting_text": "document_extraction",
        }.get(stage)
        if artifact_kind is None:
            raise ErrBadRequest()
        value = artifact(content, artifact_kind)
        return json.dumps(value, ensure_ascii=False), "json"
    if kind == "ui":
        source, _ = _frozen_inputs(source_snapshot)
        run = SimpleNamespace(snapshot_json=source)
        value = validate_ui_output(run, stage, content)
        if stage == "ui_yaml":
            return str(value), "yaml"
        return json.dumps(value, ensure_ascii=False), "json"
    if (kind, stage) == ("api", "api_design"):
        value = _strict_json_object(content)
        source, config = _frozen_inputs(source_snapshot)
        extraction = config.get("apiExtraction")
        if extraction is None:
            extraction = source.get("apiExtraction")
        _validate_api_design_shallow(value, extraction)
        return json.dumps(value, ensure_ascii=False), "json"
    if (kind, stage) in {
        ("function", "requirement_analysis"),
        ("function", "case_names"),
        ("api", "interface_extract"),
    }:
        try:
            value = json.loads(content)
        except ValueError as exc:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是合法 JSON") from exc
        if not isinstance(value, dict) or not value:
            raise dynamic_error(ErrBadRequest, "阶段产物必须是非空 JSON 对象")
        source, config = _frozen_inputs(source_snapshot)
        if kind == "function" and stage == "requirement_analysis":
            raw_material = source.get("sourceContent")
            try:
                material = _json_object(raw_material)
                validate_test_scope(value, material)
            except (ValueError, TypeError, KeyError) as exc:
                raise dynamic_error(ErrBadRequest, str(exc)) from exc
        if kind == "function" and stage == "case_names":
            raw_material = source.get("sourceContent")
            raw_analysis = config.get("requirementAnalysis")
            try:
                material = _json_object(raw_material)
                analysis = _json_object(raw_analysis)
                if material is None or analysis is None:
                    raise ValueError("测试点缺少冻结的材料或测试范围分析")
                validate_traceable_test_points(value, material, analysis)
            except (ValueError, TypeError, KeyError) as exc:
                raise dynamic_error(ErrBadRequest, str(exc)) from exc
        return json.dumps(value, ensure_ascii=False), "json"
    if kind == "function" and stage == "detailed_cases":
        cases = generated_function_cases(content)
        if not cases:
            raise ErrBadRequest()
        validate_function_candidate_cases(cases)
        return content, "yaml"
    if kind == "api" and stage == "generate":
        payload = parse_import_payload(content)
        await validate_api_collection_import_payload(repository, "", payload, check_existing=False)
        return content, "yaml"
    raise ErrBadRequest()

from __future__ import annotations

import json
from typing import Any

import yaml

from testing_agent.core.errors import (
    ErrApiCollectionImportFileRequired,
    ErrApiCollectionImportInvalid,
    ErrNotFound,
    dynamic_error,
)
from testing_agent.core.sid import new_id
from testing_agent.models.api_assert_rule import ApiAssertRule
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.api_extract_rule import ApiExtractRule
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.schemas.api_collection import ApiCollectionRequest, ApiCollectionResponse
from testing_agent.services.common import apply_patch, dump, list_payload
from testing_agent.services.project_access import ProjectAction, require_project_access

ALLOWED_IMPORT_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
ALLOWED_IMPORT_BODY_TYPES = {"json", "form", "raw", "none"}
ALLOWED_IMPORT_EXTRACT_SOURCES = {"header", "body_jsonpath", "body_text", "status_code"}
ALLOWED_IMPORT_ASSERT_SOURCES = {"status_code", "header", "body_jsonpath", "body_text"}
ALLOWED_IMPORT_COMPARATORS = {
    "eq",
    "neq",
    "contains",
    "not_contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "exists",
    "regex",
}
IMPORT_CASE_FIELDS = {
    "name",
    "description",
    "enabled",
    "orderNo",
    "method",
    "urlTemplate",
    "headers",
    "query",
    "bodyType",
    "bodyJson",
    "bodyText",
    "timeoutMs",
    "continueOnFailure",
    "extractRules",
    "assertRules",
}
IMPORT_EXTRACT_RULE_FIELDS = {
    "name",
    "enabled",
    "orderNo",
    "source",
    "sourceExpr",
    "varKey",
    "defaultValue",
}
IMPORT_ASSERT_RULE_FIELDS = {
    "name",
    "enabled",
    "orderNo",
    "assertSource",
    "targetExpr",
    "comparator",
    "expectedValue",
}


def import_error(message: str):
    return dynamic_error(ErrApiCollectionImportInvalid, message)


def parse_import_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        data = yaml.safe_load(payload) if payload.strip() else {}
        if isinstance(data, dict):
            return data
        return {"items": data or []}
    return {"items": payload or []}


async def read_import_payload(payload: Any = None, file: Any = None) -> dict[str, Any]:
    if file is not None:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
        return parse_import_payload(text)
    return parse_import_payload(payload)


def import_items(payload: Any, *keys: str) -> list[Any]:
    data = parse_import_payload(payload)
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    if isinstance(data.get("items"), list):
        return data["items"]
    return []


def normalize_json_value(value: Any) -> Any:
    if value == "":
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def normalize_import_method(method: Any) -> str:
    return str(method or "").strip().upper()


def normalize_import_body_type(body_type: Any) -> str:
    value = str(body_type or "").strip().lower()
    return value or "json"


def int_value(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise import_error("数字字段格式不合法") from exc


def require_string_map(value: Any, field_path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise import_error(f"{field_path} 必须是对象")
    return value


def check_unknown_fields(item: dict[str, Any], allowed: set[str], field_path: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise import_error(f"{field_path}.{unknown[0]} 字段不支持")


def validate_import_body(case_index: int, body_type: str, body_json: Any, body_text: str) -> None:
    if body_type in {"json", "form"}:
        if body_json is not None and not isinstance(body_json, dict):
            raise import_error(f"cases[{case_index}].bodyJson 必须是对象")
        return
    if body_type == "raw" and body_json is not None:
        raise import_error(f"cases[{case_index}].bodyType=raw 时不支持 bodyJson")
    if body_type == "none":
        if body_json is not None:
            raise import_error(f"cases[{case_index}].bodyType=none 时不支持 bodyJson")
        if str(body_text or "").strip():
            raise import_error(f"cases[{case_index}].bodyType=none 时不支持 bodyText")


async def repository_case_exists(repository: Any, collection_id: str, name: str) -> bool:
    exists = getattr(repository, "exists_case_by_collection_and_name", None)
    if exists is None:
        return False
    return bool(await exists(collection_id, name))


async def validate_api_collection_import_payload(
    repository: Any,
    collection_id: str,
    payload: dict[str, Any],
    *,
    check_existing: bool = True,
) -> list[dict[str, Any]]:
    if set(payload) - {"cases"}:
        unknown = sorted(set(payload) - {"cases"})[0]
        raise import_error(f"{unknown} 字段不支持")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise import_error("cases 不能为空")

    case_names: set[str] = set()
    for case_index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise import_error(f"cases[{case_index}] 必须是对象")
        check_unknown_fields(item, IMPORT_CASE_FIELDS, f"cases[{case_index}]")

        name = str(item.get("name") or "").strip()
        if not name:
            raise import_error(f"cases[{case_index}].name 不能为空")
        if len(name) > 120:
            raise import_error(f"cases[{case_index}].name 长度不能超过 120")
        normalized_name = name.casefold()
        if normalized_name in case_names:
            raise import_error(f"cases[{case_index}].name 与文件内其他用例重复: {name}")
        case_names.add(normalized_name)
        if check_existing and await repository_case_exists(repository, collection_id, name):
            raise import_error(f"集合内已存在同名用例: {name}")

        if len(str(item.get("description") or "")) > 512:
            raise import_error(f"cases[{case_index}].description 长度不能超过 512")
        if int_value(item.get("orderNo"), 0) < 0:
            raise import_error(f"cases[{case_index}].orderNo 不能小于 0")
        if int_value(item.get("timeoutMs"), 5000) < 0:
            raise import_error(f"cases[{case_index}].timeoutMs 不能小于 0")

        method = normalize_import_method(item.get("method"))
        if method not in ALLOWED_IMPORT_METHODS:
            allowed = " | ".join(sorted(ALLOWED_IMPORT_METHODS))
            raise import_error(f"cases[{case_index}].method 仅支持 {allowed}")
        url_template = str(item.get("urlTemplate") or "")
        if not url_template.strip():
            raise import_error(f"cases[{case_index}].urlTemplate 不能为空")
        if len(url_template) > 1024:
            raise import_error(f"cases[{case_index}].urlTemplate 长度不能超过 1024")

        body_type = normalize_import_body_type(item.get("bodyType"))
        if body_type not in ALLOWED_IMPORT_BODY_TYPES:
            allowed = " | ".join(sorted(ALLOWED_IMPORT_BODY_TYPES))
            raise import_error(f"cases[{case_index}].bodyType 仅支持 {allowed}")
        validate_import_body(
            case_index,
            body_type,
            item.get("bodyJson"),
            item.get("bodyText") or "",
        )
        require_string_map(item.get("headers"), f"cases[{case_index}].headers")
        require_string_map(item.get("query"), f"cases[{case_index}].query")

        extract_var_keys: set[str] = set()
        extract_rules = item.get("extractRules") or []
        if not isinstance(extract_rules, list):
            raise import_error(f"cases[{case_index}].extractRules 必须是数组")
        for rule_index, rule in enumerate(extract_rules):
            if not isinstance(rule, dict):
                raise import_error(f"cases[{case_index}].extractRules[{rule_index}] 必须是对象")
            check_unknown_fields(
                rule,
                IMPORT_EXTRACT_RULE_FIELDS,
                f"cases[{case_index}].extractRules[{rule_index}]",
            )
            rule_name = str(rule.get("name") or "").strip()
            if not rule_name:
                raise import_error(f"cases[{case_index}].extractRules[{rule_index}].name 不能为空")
            if len(rule_name) > 120:
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].name 长度不能超过 120"
                )
            if int_value(rule.get("orderNo"), 0) < 0:
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].orderNo 不能小于 0"
                )
            if str(rule.get("source") or "") not in ALLOWED_IMPORT_EXTRACT_SOURCES:
                allowed = " | ".join(sorted(ALLOWED_IMPORT_EXTRACT_SOURCES))
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].source 仅支持 {allowed}"
                )
            if len(str(rule.get("sourceExpr") or "")) > 512:
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].sourceExpr 长度不能超过 512"
                )
            var_key = str(rule.get("varKey") or "").strip()
            if not var_key:
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].varKey 不能为空"
                )
            if len(var_key) > 100:
                raise import_error(
                    f"cases[{case_index}].extractRules[{rule_index}].varKey 长度不能超过 100"
                )
            if var_key in extract_var_keys:
                field = f"cases[{case_index}].extractRules[{rule_index}].varKey"
                raise import_error(f"{field} 与同用例内其他提取规则重复: {var_key}")
            extract_var_keys.add(var_key)

        assert_names: set[str] = set()
        assert_rules = item.get("assertRules") or []
        if not isinstance(assert_rules, list):
            raise import_error(f"cases[{case_index}].assertRules 必须是数组")
        for rule_index, rule in enumerate(assert_rules):
            if not isinstance(rule, dict):
                raise import_error(f"cases[{case_index}].assertRules[{rule_index}] 必须是对象")
            check_unknown_fields(
                rule,
                IMPORT_ASSERT_RULE_FIELDS,
                f"cases[{case_index}].assertRules[{rule_index}]",
            )
            rule_name = str(rule.get("name") or "").strip()
            if not rule_name:
                raise import_error(f"cases[{case_index}].assertRules[{rule_index}].name 不能为空")
            if len(rule_name) > 120:
                raise import_error(
                    f"cases[{case_index}].assertRules[{rule_index}].name 长度不能超过 120"
                )
            if rule_name in assert_names:
                field = f"cases[{case_index}].assertRules[{rule_index}].name"
                raise import_error(f"{field} 与同用例内其他断言重复: {rule_name}")
            assert_names.add(rule_name)
            if int_value(rule.get("orderNo"), 0) < 0:
                raise import_error(
                    f"cases[{case_index}].assertRules[{rule_index}].orderNo 不能小于 0"
                )
            if str(rule.get("assertSource") or "") not in ALLOWED_IMPORT_ASSERT_SOURCES:
                allowed = " | ".join(sorted(ALLOWED_IMPORT_ASSERT_SOURCES))
                raise import_error(
                    f"cases[{case_index}].assertRules[{rule_index}].assertSource 仅支持 {allowed}"
                )
            if len(str(rule.get("targetExpr") or "")) > 512:
                raise import_error(
                    f"cases[{case_index}].assertRules[{rule_index}].targetExpr 长度不能超过 512"
                )
            if str(rule.get("comparator") or "") not in ALLOWED_IMPORT_COMPARATORS:
                allowed = " | ".join(sorted(ALLOWED_IMPORT_COMPARATORS))
                raise import_error(
                    f"cases[{case_index}].assertRules[{rule_index}].comparator 仅支持 {allowed}"
                )
    return cases


class ApiCollectionService:
    def __init__(self, repository: ApiCollectionRepository):
        self.repository = repository

    async def ensure_requirement_access(
        self, user_id: str, requirement_id: str, *, action: ProjectAction = "read"
    ) -> None:
        requirement = await self.repository.get_requirement(requirement_id)
        if requirement is None:
            raise ErrNotFound
        sprint = await self.repository.get_sprint(requirement.sprint_id)
        if sprint is None:
            raise ErrNotFound
        project = await self.repository.get_project(sprint.project_id)
        if project is None:
            raise ErrNotFound
        await require_project_access(self.repository.session, user_id, project, action)

    async def get_accessible_entity(
        self, user_id: str, collection_id: str, *, action: ProjectAction = "read"
    ) -> ApiCollection:
        collection = await self.repository.get_collection(collection_id)
        if collection is None:
            raise ErrNotFound
        await self.ensure_requirement_access(user_id, collection.requirement_id, action=action)
        return collection

    async def create(self, user_id: str, requirement_id: str, body: ApiCollectionRequest) -> dict:
        await self.ensure_requirement_access(user_id, requirement_id, action="write")
        collection = ApiCollection(
            collection_id=new_id(),
            requirement_id=requirement_id,
            name=body.name,
            description=body.description,
        )
        self.repository.add(collection)
        await self.repository.commit()
        await self.repository.refresh(collection)
        return dump(ApiCollectionResponse, collection)

    async def list(self, user_id: str, requirement_id: str) -> dict[str, Any]:
        await self.ensure_requirement_access(user_id, requirement_id, action="read")
        rows = await self.repository.list_by_requirement(requirement_id)
        return list_payload([dump(ApiCollectionResponse, row) for row in rows])

    async def get(self, user_id: str, collection_id: str) -> dict:
        return dump(
            ApiCollectionResponse,
            await self.get_accessible_entity(user_id, collection_id, action="read"),
        )

    async def update(self, user_id: str, collection_id: str, body: dict[str, Any]) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        apply_patch(collection, body, {"name", "description"})
        await self.repository.commit()
        await self.repository.refresh(collection)
        return dump(ApiCollectionResponse, collection)

    async def delete(self, user_id: str, collection_id: str) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        await self.repository.hard_delete(collection)
        await self.repository.commit()
        return {}

    async def import_cases(self, user_id: str, collection_id: str, payload: Any, file: Any) -> dict:
        collection = await self.get_accessible_entity(user_id, collection_id, action="write")
        if file is not None:
            filename = str(getattr(file, "filename", "") or "")
            if not filename:
                raise ErrApiCollectionImportFileRequired
            if not filename.lower().endswith((".yaml", ".yml")):
                raise import_error("仅支持导入 .yaml 或 .yml 文件")
        parsed = await read_import_payload(payload, file)
        cases = await validate_api_collection_import_payload(
            self.repository, collection.collection_id, parsed
        )
        imported_case_count = 0
        imported_extract_rule_count = 0
        imported_assert_rule_count = 0
        for index, item in enumerate(cases):
            case_id = new_id()
            body_type = normalize_import_body_type(item.get("bodyType"))
            body_json = normalize_json_value(item.get("bodyJson"))
            body_text = str(item.get("bodyText") or "")
            if body_type == "raw":
                body_json = None
            elif body_type == "none":
                body_json = None
                body_text = ""
            self.repository.add(
                ApiCase(
                    case_id=case_id,
                    collection_id=collection_id,
                    name=str(item.get("name") or f"API Case {index + 1}"),
                    description=str(item.get("description") or ""),
                    enabled=bool_value(item.get("enabled"), True),
                    order_no=int_value(item.get("orderNo"), 0),
                    method=normalize_import_method(item.get("method")),
                    url_template=str(item.get("urlTemplate") or ""),
                    headers_json=require_string_map(item.get("headers"), f"cases[{index}].headers"),
                    query_json=require_string_map(item.get("query"), f"cases[{index}].query"),
                    body_type=body_type,
                    body_json=body_json,
                    body_text=body_text,
                    timeout_ms=int_value(item.get("timeoutMs"), 5000),
                    continue_on_failure=bool_value(item.get("continueOnFailure"), False),
                )
            )
            extract_rules = item.get("extractRules")
            if isinstance(extract_rules, list):
                for rule_index, rule in enumerate(extract_rules):
                    if not isinstance(rule, dict):
                        continue
                    self.repository.add(
                        ApiExtractRule(
                            extract_rule_id=new_id(),
                            case_id=case_id,
                            name=str(rule.get("name") or f"Extract Rule {rule_index + 1}"),
                            enabled=bool_value(rule.get("enabled"), True),
                            order_no=int(rule.get("orderNo", rule_index)),
                            source=str(rule.get("source") or ""),
                            source_expr=str(rule.get("sourceExpr") or ""),
                            var_key=str(rule.get("varKey") or ""),
                            default_value=str(rule.get("defaultValue") or ""),
                        )
                    )
                    imported_extract_rule_count += 1
            assert_rules = item.get("assertRules")
            if isinstance(assert_rules, list):
                for rule_index, rule in enumerate(assert_rules):
                    if not isinstance(rule, dict):
                        continue
                    self.repository.add(
                        ApiAssertRule(
                            assert_rule_id=new_id(),
                            case_id=case_id,
                            name=str(rule.get("name") or f"Assert Rule {rule_index + 1}"),
                            enabled=bool_value(rule.get("enabled"), True),
                            order_no=int(rule.get("orderNo", rule_index)),
                            assert_source=str(rule.get("assertSource") or ""),
                            target_expr=str(rule.get("targetExpr") or ""),
                            comparator=str(rule.get("comparator") or ""),
                            expected_value=str(rule.get("expectedValue") or ""),
                        )
                    )
                    imported_assert_rule_count += 1
            imported_case_count += 1
        await self.repository.commit()
        return {
            "collectionId": collection.collection_id,
            "importedCaseCount": imported_case_count,
            "importedExtractRuleCount": imported_extract_rule_count,
            "importedAssertRuleCount": imported_assert_rule_count,
        }

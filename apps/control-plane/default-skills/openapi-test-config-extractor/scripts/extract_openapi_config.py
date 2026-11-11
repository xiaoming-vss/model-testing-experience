#!/usr/bin/env python3
"""OpenAPI 配置提取脚本。

调用链路：
- 该脚本可作为 `openapi-test-config-extractor` skill 的参考实现
- 输入 OpenAPI/Swagger JSON
- 输出接口测试配置字典，供后续 YAML 生成链路消费
"""

import argparse
import json
import re
from pathlib import Path


LOGIN_NOISE_BLACKLIST = {"grant_type", "scope", "client_id", "client_secret"}
KEY_EXTRACTION_FIELDS = {"id", "access_token", "token"}


def load_spec(path: Path):
    """读取 OpenAPI/Swagger JSON 文件。

    调用链路：`main -> load_spec`
    """

    return json.loads(path.read_text(encoding="utf-8"))


def resolve_ref(spec, ref):
    """解析 `$ref` 引用。

    调用链路：`deref/schema_to_response/object_fields -> resolve_ref`
    """

    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported ref: {ref}")
    node = spec
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def deref(spec, schema):
    """递归展开 schema 中的 `$ref`。

    调用链路：多个 schema 处理辅助函数都会先经过 `deref`
    """

    while isinstance(schema, dict) and "$ref" in schema:
        schema = resolve_ref(spec, schema["$ref"])
    return schema


def pick_non_null_anyof(spec, schema):
    """从 `anyOf` 中挑出非空分支。

    调用链路：`infer_type/field_string/object_fields/schema_to_response`
    """

    any_of = schema.get("anyOf")
    if not any_of:
        return schema, False
    non_null = [deref(spec, item) for item in any_of if item.get("type") != "null"]
    has_null = any(item.get("type") == "null" for item in any_of)
    if len(non_null) == 1:
        return non_null[0], has_null
    return schema, has_null


def is_login_or_auth(operation, path):
    """判断接口是否属于登录/认证类接口。

    调用链路：`extract_operation -> is_login_or_auth`
    """

    text = " ".join(
        str(v)
        for v in [
            path,
            operation.get("summary", ""),
            operation.get("operationId", ""),
            " ".join(operation.get("tags", [])),
        ]
    ).lower()
    return any(token in text for token in ["login", "auth", "token", "signin", "sign_in"])


def to_snake_case(text):
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    return text or "api"


def endpoint_key(path, method, operation):
    """生成输出字典里的稳定接口键名。

    调用链路：`main -> endpoint_key`
    """

    if operation.get("summary"):
        return to_snake_case(operation["summary"])
    if operation.get("operationId"):
        return to_snake_case(operation["operationId"])
    return to_snake_case(f"{method}_{path}")


def infer_type(spec, schema):
    """推断字段类型。

    调用链路：`field_string/schema_to_response -> infer_type`
    """

    schema = deref(spec, schema)
    schema, _ = pick_non_null_anyof(spec, schema)

    if schema.get("type") == "array":
        return "array"
    if schema.get("type") == "object":
        return "object"
    if "enum" in schema and "type" not in schema:
        return "string"
    return schema.get("type", "object")


def collect_constraints(schema):
    constraints = []
    for key in [
        "maxLength",
        "minLength",
        "format",
        "default",
        "minimum",
        "maximum",
        "pattern",
        "enum",
    ]:
        if key in schema:
            value = schema[key]
            if isinstance(value, list):
                value = "|".join(str(v) for v in value)
            constraints.append(f"{key}:{value}")
    return constraints


def mark_key_extraction(name, field_str):
    lower = name.lower()
    if lower in KEY_EXTRACTION_FIELDS or lower.endswith("_id"):
        suffix = "# [关键提取] 用于后续操作传承"
        if "#" in field_str:
            return field_str.replace("#", f"{suffix} #", 1)
        return f"{field_str} {suffix}"
    return field_str


def field_string(spec, name, schema, required, mark_keys=False):
    """把字段 schema 渲染成人类可读的说明字符串。

    调用链路：`object_fields/collect_parameters -> field_string`
    """

    schema = deref(spec, schema)
    schema, nullable = pick_non_null_anyof(spec, schema)

    field_type = infer_type(spec, schema)
    if field_type == "object" and schema.get("additionalProperties") is True:
        status = "可选" if (nullable or not required) else "必传"
        result = f"object ({status}, 允许任意键值对/any)"
        return mark_key_extraction(name, result) if mark_keys else result

    parts = ["必传" if required and not nullable else "可选"]
    parts.extend(collect_constraints(schema))

    desc = schema.get("description")
    result = f"{field_type} ({', '.join(parts)})"
    if desc:
        result = f"{result} # {desc}"
    return mark_key_extraction(name, result) if mark_keys else result


def object_fields(spec, schema, mark_keys=False, login_noise_filter=False):
    """提取对象字段定义。

    调用链路：
    - `extract_operation` 处理请求体时调用
    - `schema_to_response` 处理响应体时调用
    """

    schema = deref(spec, schema)
    schema, _ = pick_non_null_anyof(spec, schema)

    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    result = {}

    for name, sub_schema in props.items():
        if login_noise_filter and name in LOGIN_NOISE_BLACKLIST:
            continue
        result[name] = field_string(spec, name, sub_schema, name in required, mark_keys=mark_keys)
    return result


def schema_to_response(spec, schema):
    """把响应 schema 转成输出字典结构。

    调用链路：`extract_operation -> schema_to_response`
    """

    schema = deref(spec, schema)
    schema, _ = pick_non_null_anyof(spec, schema)

    if schema.get("type") == "array":
        items = deref(spec, schema.get("items", {}))
        if items.get("type") == "object" or items.get("properties") or "$ref" in schema.get("items", {}):
            return [object_fields(spec, items, mark_keys=True)]
        return [infer_type(spec, items)]

    if schema.get("type") == "object" or schema.get("properties"):
        return object_fields(spec, schema, mark_keys=True)

    return infer_type(spec, schema)


def extract_headers(operation, body_content_type):
    """推导请求头。

    调用链路：`extract_operation -> extract_headers`
    """

    headers = {}
    if body_content_type:
        headers["Content-Type"] = f"{body_content_type} # [必传]"
    if operation.get("security"):
        headers["Authorization"] = "Bearer {access_token} # [必传]"
    return headers


def collect_parameters(spec, parameters):
    """采集 path/query/header 参数。

    调用链路：`extract_operation -> collect_parameters`
    """

    path_params = {}
    query = {}
    headers = {}

    for param in parameters:
        param = deref(spec, param)
        name = param["name"]
        where = param["in"]
        schema = param.get("schema", {})
        field = field_string(spec, name, schema, param.get("required", False))
        if param.get("description") and "#" not in field:
            field = f"{field} # {param['description']}"

        if where == "path":
            path_params[name] = field
        elif where == "query":
            query[name] = field
        elif where == "header":
            headers[name] = field

    result = {}
    if headers:
        result["headers"] = headers
    if path_params:
        result["path_params"] = path_params
    if query:
        result["query"] = query
    return result


def pick_success_response(operation):
    """选择优先级最高的成功响应定义。

    调用链路：`extract_operation -> pick_success_response`
    """

    responses = operation.get("responses", {})
    for code in ["200", "201", "202", "204"]:
        if code in responses:
            return responses[code]
    for code, response in responses.items():
        if str(code).startswith("2"):
            return response
    return None


def pick_body_schema(spec, operation):
    """选择请求体 schema 及其归属区域。

    调用链路：`extract_operation -> pick_body_schema`
    """

    request_body = operation.get("requestBody")
    if not request_body:
        return None, None, None

    request_body = deref(spec, request_body)
    content = request_body.get("content", {})
    for content_type in [
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ]:
        if content_type in content:
            schema = content[content_type].get("schema", {})
            section = "json" if content_type == "application/json" else "data"
            return content_type, section, schema

    if content:
        content_type, media = next(iter(content.items()))
        section = "json" if content_type == "application/json" else "data"
        return content_type, section, media.get("schema", {})

    return None, None, None


def should_include_endpoint(path, method, operation, endpoint_filters, keywords):
    """判断接口是否应进入最终输出。

    调用链路：`main -> should_include_endpoint`
    """

    endpoint_name = f"{method.upper()}:{path}"
    haystack = " ".join(
        [
            path,
            method,
            operation.get("summary", ""),
            operation.get("operationId", ""),
            " ".join(operation.get("tags", [])),
        ]
    ).lower()

    matches_endpoint = endpoint_name in endpoint_filters if endpoint_filters else False
    matches_keyword = any(keyword.lower() in haystack for keyword in keywords) if keywords else False

    if endpoint_filters and keywords:
        return matches_endpoint or matches_keyword
    if endpoint_filters:
        return matches_endpoint
    if keywords:
        return matches_keyword
    return True


def extract_operation(spec, path, method, operation, path_item):
    """提取单个接口的测试配置。

    调用链路：
    - `main -> extract_operation`
    - `extract_operation -> collect_parameters/pick_body_schema/schema_to_response`
    """

    result = {
        "path": path,
        "method": method.upper(),
    }

    content_type, body_section, body_schema = pick_body_schema(spec, operation)

    collected = collect_parameters(spec, path_item.get("parameters", []) + operation.get("parameters", []))
    merged_headers = collected.pop("headers", {})
    final_headers = {**merged_headers, **extract_headers(operation, content_type)}
    if final_headers:
        result["headers"] = final_headers

    result.update(collected)

    if body_schema:
        noise_filter = body_section == "data" and is_login_or_auth(operation, path)
        result[body_section] = object_fields(
            spec,
            body_schema,
            mark_keys=False,
            login_noise_filter=noise_filter,
        )

    success_response = pick_success_response(operation)
    if success_response:
        content = deref(spec, success_response).get("content", {})
        if "application/json" in content:
            response_schema = content["application/json"].get("schema", {})
            result["response"] = schema_to_response(spec, response_schema)

    return result


def main():
    """命令行入口。

    调用链路：
    - `python extract_openapi_config.py --input ...`
    - `main -> load_spec -> 遍历 paths -> extract_operation -> print JSON`
    """

    parser = argparse.ArgumentParser(description="Extract OpenAPI JSON into test config dictionary.")
    parser.add_argument("--input", required=True, help="Path to OpenAPI or Swagger JSON file")
    parser.add_argument(
        "--endpoint",
        action="append",
        default=[],
        help="Exact endpoint selector in METHOD:/path form, for example POST:/auth/login",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Fuzzy keyword filter matched against path, summary, operationId, and tags",
    )
    args = parser.parse_args()

    spec = load_spec(Path(args.input))
    paths = spec.get("paths", {})
    output = {}

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not should_include_endpoint(path, method, operation, args.endpoint, args.keyword):
                continue
            key = endpoint_key(path, method, operation)
            output[key] = extract_operation(spec, path, method, operation, path_item)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

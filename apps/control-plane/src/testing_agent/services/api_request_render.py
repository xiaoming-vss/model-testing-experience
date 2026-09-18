from __future__ import annotations

import json
import random
import re
import string
import time
import uuid
from dataclasses import dataclass
from typing import Any

TEMPLATE_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
EXACT_TEMPLATE_RE = re.compile(r"^{{\s*([^{}]+?)\s*}}$")


@dataclass(frozen=True)
class RenderedApiCaseRequest:
    snapshot: dict[str, Any]
    runtime_vars: dict[str, str]


def render_api_case_request(
    api_case: Any,
    environment: Any,
    env_vars: list[Any],
) -> RenderedApiCaseRequest:
    variables = {item.var_key: item.value for item in env_vars}
    base_url = render_template_string(getattr(environment, "base_url", ""), variables)
    url_template = render_template_string(getattr(api_case, "url_template", ""), variables)
    final_url = join_base_url(base_url, url_template)
    headers = render_string_map_json(getattr(api_case, "headers_json", None), variables)
    query = render_string_map_json(getattr(api_case, "query_json", None), variables)
    body_type = getattr(api_case, "body_type", "json") or "json"
    snapshot = {
        "method": getattr(api_case, "method", ""),
        "url": final_url,
        "headersJson": json_compact(headers),
        "queryJson": json_compact(query),
        "bodyType": body_type,
        "body": "",
    }

    if body_type == "json":
        snapshot["body"] = render_json_body(getattr(api_case, "body_json", None), variables)
    elif body_type == "form":
        snapshot["body"] = json_compact(
            render_string_map_json(getattr(api_case, "body_json", None), variables)
        )
    elif body_type == "raw":
        snapshot["body"] = render_template_string(getattr(api_case, "body_text", ""), variables)
    elif body_type == "none":
        snapshot["body"] = ""
    else:
        snapshot["body"] = render_json_body(getattr(api_case, "body_json", None), variables)

    return RenderedApiCaseRequest(snapshot=snapshot, runtime_vars=dict(variables))


def api_case_request_template(api_case: Any, environment: Any) -> dict[str, Any]:
    body_type = getattr(api_case, "body_type", "json") or "json"
    headers_json = normalize_json_input(getattr(api_case, "headers_json", None)) or {}
    query_json = normalize_json_input(getattr(api_case, "query_json", None)) or {}
    body_json = normalize_json_input(getattr(api_case, "body_json", None))
    return {
        "method": getattr(api_case, "method", ""),
        "baseUrl": getattr(environment, "base_url", ""),
        "urlTemplate": getattr(api_case, "url_template", ""),
        "headersJson": json_compact(headers_json),
        "queryJson": json_compact(query_json),
        "bodyType": body_type,
        "bodyJson": (
            json_compact(body_json)
            if body_type in {"json", "form"} and body_json is not None
            else ""
        ),
        "bodyText": getattr(api_case, "body_text", ""),
        "timeoutMs": getattr(api_case, "timeout_ms", 5000),
    }


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def normalize_json_input(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def render_string_map_json(value: Any, variables: dict[str, str]) -> dict[str, str]:
    raw = normalize_json_input(value)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("expected JSON object")
    result: dict[str, str] = {}
    for key, item in raw.items():
        rendered_key = render_template_string(str(key), variables)
        rendered_value = render_json_value(item, variables)
        result[rendered_key] = stringify_value(rendered_value)
    return result


def render_json_body(value: Any, variables: dict[str, str]) -> str:
    raw = normalize_json_input(value)
    if raw is None:
        return ""
    return json_compact(render_json_value(raw, variables))


def render_json_value(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        exact = EXACT_TEMPLATE_RE.match(value)
        if exact:
            resolved = resolve_template_expression(exact.group(1).strip(), variables)
            if resolved is not None:
                return resolved
        return render_template_string(value, variables)
    if isinstance(value, list):
        return [render_json_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {
            render_template_string(str(key), variables): render_json_value(item, variables)
            for key, item in value.items()
        }
    return value


def render_template_string(value: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        resolved = resolve_template_expression(match.group(1).strip(), variables)
        if resolved is None:
            return match.group(0)
        return stringify_value(resolved)

    return TEMPLATE_RE.sub(replace, value or "")


def resolve_template_expression(expr: str, variables: dict[str, str]) -> Any:
    if not expr:
        return None
    if expr.startswith("$"):
        return resolve_dynamic_expression(expr)
    return variables.get(expr)


def resolve_dynamic_expression(expr: str) -> Any:
    if expr == "$timestamp":
        return int(time.time())
    if expr == "$timestamp_ms":
        return int(time.time() * 1000)
    if expr == "$now":
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if expr == "$uuid":
        return str(uuid.uuid4())
    parts = expr.split()
    if len(parts) == 3 and parts[0] == "$randomInt":
        return random.randint(int(parts[1]), int(parts[2]))
    if len(parts) == 2 and parts[0] == "$randomString":
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choice(alphabet) for _ in range(int(parts[1])))
    return None


def join_base_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    if not base_url.strip():
        return path
    if not path.strip():
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

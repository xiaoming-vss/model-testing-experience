from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from testing_agent.domain.template_functions import evaluate_function, is_function

TEMPLATE_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")


@dataclass(frozen=True)
class RenderedApiCaseRequest:
    snapshot: dict[str, Any]
    runtime_vars: dict[str, str]


def render_api_case_request(
    api_case: Any,
    environment: Any,
    env_vars: list[Any],
) -> RenderedApiCaseRequest:
    """Pre-render the snapshot a run starts with; the Worker renders the request it sends."""
    variables = {item.var_key: item.value for item in env_vars}
    builtins: dict[str, str] = {}
    base_url = render_template_string(getattr(environment, "base_url", ""), variables, builtins)
    url_template = render_template_string(
        getattr(api_case, "url_template", ""), variables, builtins
    )
    final_url = join_base_url(base_url, url_template)
    headers = render_string_map_json(getattr(api_case, "headers_json", None), variables, builtins)
    query = render_string_map_json(getattr(api_case, "query_json", None), variables, builtins)
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
        snapshot["body"] = render_json_body(
            getattr(api_case, "body_json", None), variables, builtins
        )
    elif body_type == "form":
        snapshot["body"] = json_compact(
            render_string_map_json(getattr(api_case, "body_json", None), variables, builtins)
        )
    elif body_type == "raw":
        snapshot["body"] = render_template_string(
            getattr(api_case, "body_text", ""), variables, builtins
        )
    elif body_type == "none":
        snapshot["body"] = ""
    else:
        snapshot["body"] = render_json_body(
            getattr(api_case, "body_json", None), variables, builtins
        )

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


def render_string_map_json(
    value: Any, variables: dict[str, str], builtins: dict[str, str] | None = None
) -> dict[str, str]:
    raw = normalize_json_input(value)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("expected JSON object")
    result: dict[str, str] = {}
    for key, item in raw.items():
        rendered_key = render_template_string(str(key), variables, builtins)
        rendered_value = render_json_value(item, variables, builtins)
        result[rendered_key] = stringify_value(rendered_value)
    return result


def render_json_body(
    value: Any, variables: dict[str, str], builtins: dict[str, str] | None = None
) -> str:
    raw = normalize_json_input(value)
    if raw is None:
        return ""
    return json_compact(render_json_value(raw, variables, builtins))


def render_json_value(
    value: Any, variables: dict[str, str], builtins: dict[str, str] | None = None
) -> Any:
    # Templates only occur inside JSON text, so a variable or function always
    # resolves to a string; this is exactly how the Worker renders the request.
    if isinstance(value, str):
        return render_template_string(value, variables, builtins)
    if isinstance(value, list):
        return [render_json_value(item, variables, builtins) for item in value]
    if isinstance(value, dict):
        return {
            render_template_string(str(key), variables, builtins): render_json_value(
                item, variables, builtins
            )
            for key, item in value.items()
        }
    return value


def render_template_string(
    value: str, variables: dict[str, str], builtins: dict[str, str] | None = None
) -> str:
    def replace(match: re.Match[str]) -> str:
        resolved = resolve_template_expression(match.group(1).strip(), variables, builtins)
        if resolved is None:
            return match.group(0)
        return resolved

    return TEMPLATE_RE.sub(replace, value or "")


def resolve_template_expression(
    expr: str, variables: dict[str, str], builtins: dict[str, str] | None = None
) -> str | None:
    """A named variable or built-in function, as text; None leaves the placeholder in place."""
    if not expr:
        return None
    if is_function(expr):
        return evaluate_function(expr, {} if builtins is None else builtins)
    return variables.get(expr)


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

"""API case runner."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .http_client import execute_request
from .rule_runtime import run_assert_rules, run_extract_rules
from .template_runtime import dump_runtime_vars, load_runtime_vars, render_json_body, render_json_map, render_template


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApiCaseRunner:
    """Runs a single API case snapshot and returns a worker completion payload."""

    async def run(self, snapshot: dict[str, Any], runtime_vars: dict[str, str] | None = None) -> dict[str, Any]:
        started_at = now_iso()
        started_monotonic = time.monotonic()
        vars_map = load_runtime_vars(snapshot.get("runtimeVarsJson"))
        if runtime_vars:
            vars_map.update(runtime_vars)

        request_snapshot: dict[str, Any]
        response_snapshot: dict[str, Any] = {"statusCode": 0, "headersJson": "{}", "body": ""}
        extract_results: list[dict[str, Any]] = []
        assert_results: list[dict[str, Any]] = []
        error_message = ""

        try:
            request_snapshot, request = build_request(snapshot, vars_map)
            response_snapshot = await execute_request(request, request.get("timeoutMs", 30000))
            extract_results = run_extract_rules(snapshot.get("extractRules", []), response_snapshot, vars_map)
            assert_results = run_assert_rules(snapshot.get("assertRules", []), response_snapshot, vars_map)
            status = "failed" if _has_rule_failure(extract_results, assert_results) else "success"
            success = status == "success"
        except Exception as exc:
            request_snapshot = snapshot.get("request", {}) or {}
            status = "error"
            success = False
            error_message = str(exc)

        finished_at = now_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        return {
            "taskId": snapshot.get("taskId", ""),
            "runId": snapshot.get("runId", ""),
            "collectionRunId": snapshot.get("collectionRunId", ""),
            "collectionId": snapshot.get("collectionId", ""),
            "caseId": snapshot.get("caseId", ""),
            "status": status,
            "success": success,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationMs": duration_ms,
            "errorMessage": error_message,
            "request": request_snapshot,
            "response": response_snapshot,
            "runtimeVarsJson": dump_runtime_vars(vars_map),
            "extractResults": extract_results,
            "assertResults": assert_results,
        }


def build_request(snapshot_request: dict[str, Any], runtime_vars: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    request_template = snapshot_request.get("requestTemplate")
    if isinstance(request_template, dict):
        return build_request_from_template(request_template, runtime_vars)

    return build_request_from_rendered_snapshot(snapshot_request.get("request", snapshot_request), runtime_vars)


def build_request_from_template(template: dict[str, Any], runtime_vars: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    method = (template.get("method") or "GET").upper()
    base_url = render_template(template.get("baseUrl", ""), runtime_vars)
    url_template = render_template(template.get("urlTemplate", ""), runtime_vars)
    url = join_base_url(base_url, url_template)
    headers = render_json_map(template.get("headersJson", "{}"), runtime_vars)
    query = render_json_map(template.get("queryJson", "{}"), runtime_vars)
    body_type = template.get("bodyType") or "none"
    body = ""
    request: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "query": query,
        "timeoutMs": template.get("timeoutMs", 30000),
    }

    if body_type == "json" and template.get("bodyJson"):
        json_body, rendered_body = render_json_body(template.get("bodyJson"), runtime_vars)
        request["json"] = json_body
        body = rendered_body
    elif body_type == "form" and template.get("bodyJson"):
        form_body = render_json_map(template.get("bodyJson"), runtime_vars)
        request["data"] = form_body
        body = json.dumps(form_body, ensure_ascii=False, separators=(",", ":"))
    elif body_type == "raw" and template.get("bodyText"):
        body = render_template(template.get("bodyText"), runtime_vars)
        request["content"] = body

    request_snapshot = {
        "method": method,
        "url": url,
        "headersJson": json.dumps(headers, ensure_ascii=False, separators=(",", ":")),
        "queryJson": json.dumps(query, ensure_ascii=False, separators=(",", ":")),
        "bodyType": body_type,
        "body": body,
    }
    return request_snapshot, request


def build_request_from_rendered_snapshot(snapshot_request: dict[str, Any], runtime_vars: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    method = (snapshot_request.get("method") or "GET").upper()
    url = render_template(snapshot_request.get("url", ""), runtime_vars)
    headers = render_json_map(snapshot_request.get("headersJson", "{}"), runtime_vars)
    query = render_json_map(snapshot_request.get("queryJson", "{}"), runtime_vars)
    body_type = snapshot_request.get("bodyType") or "none"
    body = render_template(snapshot_request.get("body", ""), runtime_vars)
    request: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "query": query,
        "timeoutMs": snapshot_request.get("timeoutMs", 30000),
    }

    if body_type == "json" and body:
        json_body, rendered_body = render_json_body(body, runtime_vars)
        request["json"] = json_body
        body = rendered_body
    elif body_type == "form" and body:
        form_body = render_json_map(body, runtime_vars)
        request["data"] = form_body
        body = json.dumps(form_body, ensure_ascii=False, separators=(",", ":"))
    elif body_type == "raw" and body:
        request["content"] = body

    request_snapshot = {
        "method": method,
        "url": url,
        "headersJson": json.dumps(headers, ensure_ascii=False, separators=(",", ":")),
        "queryJson": json.dumps(query, ensure_ascii=False, separators=(",", ":")),
        "bodyType": body_type,
        "body": body,
    }
    return request_snapshot, request


def join_base_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    if not base_url.strip():
        return path
    if not path.strip():
        return base_url.rstrip("/")
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _has_rule_failure(extract_results: list[dict[str, Any]], assert_results: list[dict[str, Any]]) -> bool:
    return any(not result.get("success", False) for result in extract_results + assert_results)

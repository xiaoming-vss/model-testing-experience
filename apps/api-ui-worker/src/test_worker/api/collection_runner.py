"""API collection runner."""

from __future__ import annotations

import time
from typing import Any

from .case_runner import ApiCaseRunner, now_iso
from .template_runtime import dump_runtime_vars, load_runtime_vars


class ApiCollectionRunner:
    """Runs API collection snapshots sequentially."""

    def __init__(self, control_plane_client: Any, case_runner: ApiCaseRunner | None = None) -> None:
        self._control_plane_client = control_plane_client
        self._case_runner = case_runner or ApiCaseRunner()

    async def run(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        started_at = now_iso()
        started_monotonic = time.monotonic()
        runtime_vars: dict[str, str] = {}
        status_counts = {"success": 0, "failed": 0, "error": 0, "skipped": 0}
        halted = False
        last_error = ""

        for item in snapshot.get("items", []):
            item_id = item.get("itemId", "")
            case_run = item.get("caseRun", {}) or {}
            if not runtime_vars:
                runtime_vars.update(load_runtime_vars(case_run.get("runtimeVarsJson")))

            if not item.get("enabled", True):
                result = _skipped_item_result(case_run, "用例未启用", runtime_vars)
                status_counts["skipped"] += 1
                self._control_plane_client.report_api_collection_item_completed(snapshot["taskId"], item_id, result)
                continue

            if halted:
                result = _skipped_item_result(case_run, "前置用例失败且未开启 continueOnFailure", runtime_vars)
                status_counts["skipped"] += 1
                self._control_plane_client.report_api_collection_item_completed(snapshot["taskId"], item_id, result)
                continue

            item_started_at = now_iso()
            self._control_plane_client.report_api_collection_item_started(snapshot["taskId"], item_id, {
                "runId": case_run.get("runId", ""),
                "caseId": case_run.get("caseId", ""),
                "startedAt": item_started_at,
            })
            result = await self._case_runner.run(case_run, runtime_vars)
            result["startedAt"] = item_started_at
            runtime_vars.update(load_runtime_vars(result.get("runtimeVarsJson")))
            self._control_plane_client.report_api_collection_item_completed(snapshot["taskId"], item_id, result)

            item_status = result.get("status", "error")
            status_counts[item_status] = status_counts.get(item_status, 0) + 1
            if item_status in ("failed", "error"):
                last_error = result.get("errorMessage") or last_error
                if not item.get("continueOnFailure", False):
                    halted = True

        final_status = _collection_status(status_counts)
        finished_at = now_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        return {
            "taskId": snapshot.get("taskId", ""),
            "runId": snapshot.get("runId", ""),
            "collectionRunId": snapshot.get("collectionRunId", ""),
            "collectionId": snapshot.get("collectionId", ""),
            "status": final_status,
            "success": final_status == "success",
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationMs": duration_ms,
            "errorMessage": last_error,
            "runtimeVarsJson": dump_runtime_vars(runtime_vars),
            "extractResults": [],
            "assertResults": [],
        }


def _skipped_item_result(case_run: dict[str, Any], reason: str, runtime_vars: dict[str, str]) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "runId": case_run.get("runId", ""),
        "caseId": case_run.get("caseId", ""),
        "status": "skipped",
        "success": False,
        "startedAt": timestamp,
        "finishedAt": timestamp,
        "durationMs": 0,
        "errorMessage": reason,
        "request": case_run.get("request", {}) or {},
        "response": {"statusCode": 0, "headersJson": "{}", "body": ""},
        "runtimeVarsJson": dump_runtime_vars(runtime_vars),
        "extractResults": [],
        "assertResults": [],
    }


def _collection_status(counts: dict[str, int]) -> str:
    if counts.get("error", 0) > 0:
        return "error"
    if counts.get("failed", 0) > 0:
        return "failed"
    return "success"

"""
控制面客户端模块
与 Go 服务端通信，领取任务、上报结果
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from ..core import logger
from ..core.artifact_server import build_artifact_url
from ..contracts.types import (
    UiCaseRunResult,
    UiSuiteItemRunResult,
    UiSuiteItemStartedPayload,
    UiSuiteRunResult,
    UiTaskHeartbeatPayload,
    UiTaskStartedPayload,
    UiWorkerTask,
    UiWorkerTaskSnapshotResponse,
    WorkerConfig,
)


class ControlPlaneClient:
    """控制面客户端类"""

    def __init__(self, config: WorkerConfig) -> None:
        """
        初始化控制面客户端

        Args:
            config: 工作配置
        """
        self._config = config
        self._client = httpx.Client(
            base_url=config.control_plane_base_url.rstrip("/"),
            headers={
                "Content-Type": "application/json",
                "X-Worker-Token": config.worker_token,
            },
            timeout=config.request_timeout_ms / 1000,
        )

    def claim_task(self) -> UiWorkerTask | None:
        """
        领取任务

        Returns:
            任务对象，如果没有可用任务则返回 None
        """
        data = self._request("POST", "/internal/ui-worker/tasks/claim", {
            "workerId": self._config.worker_id,
        })
        if data is None:
            return None
        return UiWorkerTask(
            task_id=data.get("taskId", ""),
            task_type=data.get("taskType", "case_debug"),
            run_id=data.get("runId", ""),
            suite_id=data.get("suiteId", ""),
            case_id=data.get("caseId", ""),
            lease_seconds=data.get("leaseSeconds", 0),
        )

    def claim_api_task(self) -> dict[str, Any] | None:
        """领取 API worker 任务。"""
        data = self._request("POST", "/internal/api-worker/tasks/claim", {
            "workerId": self._config.worker_id,
        })
        return data

    def get_api_task_snapshot(self, task_id: str) -> dict[str, Any]:
        """获取 API worker 任务快照。"""
        data = self._request("GET", f"/internal/api-worker/tasks/{task_id}/snapshot")
        if data is None:
            raise ValueError(f"api task {task_id} snapshot is empty")
        return data

    def report_api_task_started(self, task_id: str, started_at: str) -> None:
        """上报 API 任务开始。"""
        self._request("POST", f"/internal/api-worker/tasks/{task_id}/started", {
            "workerId": self._config.worker_id,
            "startedAt": started_at,
        })

    def report_api_task_heartbeat(self, task_id: str, heartbeat_at: str) -> None:
        """上报 API 任务心跳。"""
        self._request("POST", f"/internal/api-worker/tasks/{task_id}/heartbeat", {
            "workerId": self._config.worker_id,
            "heartbeatAt": heartbeat_at,
        })

    def report_api_collection_item_started(self, task_id: str, item_id: str, payload: dict[str, Any]) -> None:
        """上报 API collection item 开始。"""
        body = {
            "workerId": self._config.worker_id,
            **payload,
        }
        self._request("POST", f"/internal/api-worker/tasks/{task_id}/collection-items/{item_id}/started", body)

    def report_api_collection_item_completed(self, task_id: str, item_id: str, payload: dict[str, Any]) -> None:
        """上报 API collection item 完成。"""
        body = {
            "workerId": self._config.worker_id,
            **payload,
        }
        self._request("POST", f"/internal/api-worker/tasks/{task_id}/collection-items/{item_id}/completed", body)

    def report_api_task_completed(self, task_id: str, payload: dict[str, Any]) -> None:
        """上报 API 任务完成。"""
        body = {
            "workerId": self._config.worker_id,
            **payload,
        }
        self._request("POST", f"/internal/api-worker/tasks/{task_id}/completed", body)

    def get_task_snapshot(self, task_id: str) -> UiWorkerTaskSnapshotResponse:
        """
        获取任务快照

        Args:
            task_id: 任务 ID

        Returns:
            任务快照响应

        Raises:
            ValueError: 快照为空时抛出
        """
        data = self._request("GET", f"/internal/ui-worker/tasks/{task_id}/snapshot")
        if data is None:
            raise ValueError(f"task {task_id} snapshot is empty")

        # 解析快照数据
        task_type = data.get("taskType", "case_debug")
        case_run = None
        suite_run = None

        if task_type == "case_debug" and "caseRun" in data:
            case_run_data = {
                **data["caseRun"],
                "taskId": data["caseRun"].get("taskId") or data.get("taskId") or task_id,
            }
            case_run = self._parse_case_run_snapshot(case_run_data)
        elif task_type == "suite_run" and "suiteRun" in data:
            suite_run_data = {
                **data["suiteRun"],
                "taskId": data["suiteRun"].get("taskId") or data.get("taskId") or task_id,
                "runId": data["suiteRun"].get("runId") or data["suiteRun"].get("suiteRunId") or data.get("runId", ""),
            }
            suite_run = self._parse_suite_run_snapshot(suite_run_data)

        return UiWorkerTaskSnapshotResponse(
            task_type=task_type,
            case_run=case_run,
            suite_run=suite_run,
        )

    def report_task_started(self, task_id: str, payload: UiTaskStartedPayload) -> None:
        """
        上报任务开始

        Args:
            task_id: 任务 ID
            payload: 开始负载
        """
        self._request("POST", f"/internal/ui-worker/tasks/{task_id}/started", asdict(payload))

    def report_task_heartbeat(self, task_id: str, payload: UiTaskHeartbeatPayload) -> None:
        """
        上报心跳

        Args:
            task_id: 任务 ID
            payload: 心跳负载
        """
        self._request("POST", f"/internal/ui-worker/tasks/{task_id}/heartbeat", asdict(payload))

    def report_suite_item_started(self, task_id: str, item_id: str, payload: UiSuiteItemStartedPayload) -> None:
        """
        上报测试集项开始

        Args:
            task_id: 任务 ID
            item_id: 测试集项 ID
            payload: 开始负载
        """
        body = {
            "workerId": self._config.worker_id,
            **asdict(payload),
        }
        self._request("POST", f"/internal/ui-worker/tasks/{task_id}/suite-items/{item_id}/started", body)

    def report_suite_item_completed(self, task_id: str, item_id: str, payload: UiSuiteItemRunResult) -> None:
        """
        上报测试集项完成

        Args:
            task_id: 任务 ID
            item_id: 测试集项 ID
            payload: 完成负载
        """
        body = {
            "workerId": self._config.worker_id,
            **self._serialize_suite_item_result(payload),
        }
        self._request("POST", f"/internal/ui-worker/tasks/{task_id}/suite-items/{item_id}/completed", body)

    def report_task_completed(self, task_id: str, payload: UiCaseRunResult | UiSuiteRunResult) -> None:
        """
        上报任务完成

        Args:
            task_id: 任务 ID
            payload: 完成负载
        """
        body = {
            "workerId": self._config.worker_id,
            **self._serialize_task_result(payload),
        }
        self._request("POST", f"/internal/ui-worker/tasks/{task_id}/completed", body)

    def log_planned_contract(self) -> None:
        """记录 API 契约"""
        logger.info("control plane contract", {
            "claim": "/internal/ui-worker/tasks/claim",
            "apiClaim": "/internal/api-worker/tasks/claim",
            "snapshot": "/internal/ui-worker/tasks/{taskId}/snapshot",
            "apiSnapshot": "/internal/api-worker/tasks/{taskId}/snapshot",
            "started": "/internal/ui-worker/tasks/{taskId}/started",
            "apiStarted": "/internal/api-worker/tasks/{taskId}/started",
            "heartbeat": "/internal/ui-worker/tasks/{taskId}/heartbeat",
            "apiHeartbeat": "/internal/api-worker/tasks/{taskId}/heartbeat",
            "suiteItemStarted": "/internal/ui-worker/tasks/{taskId}/suite-items/{itemId}/started",
            "suiteItemCompleted": "/internal/ui-worker/tasks/{taskId}/suite-items/{itemId}/completed",
            "apiCollectionItemStarted": "/internal/api-worker/tasks/{taskId}/collection-items/{itemId}/started",
            "apiCollectionItemCompleted": "/internal/api-worker/tasks/{taskId}/collection-items/{itemId}/completed",
            "completed": "/internal/ui-worker/tasks/{taskId}/completed",
            "apiCompleted": "/internal/api-worker/tasks/{taskId}/completed",
        })

    def _request(self, method: str, pathname: str, body: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            pathname: 请求路径
            body: 请求体

        Returns:
            响应数据，如果状态码为 204 则返回 None

        Raises:
            httpx.HTTPStatusError: HTTP 状态码错误时抛出
        """
        try:
            if body is not None:
                response = self._client.request(method, pathname, json=body)
            else:
                response = self._client.request(method, pathname)

            if response.status_code == 204:
                return None

            response.raise_for_status()

            text = response.text
            if not text:
                return None

            return self._unwrap_response_data(response.json())
        except httpx.HTTPStatusError as e:
            raise Exception(f"control plane request failed: {method} {pathname} -> {e.response.status_code} {e.response.text}") from e
        except Exception as e:
            raise Exception(f"control plane request failed: {method} {pathname} -> {str(e)}") from e

    def _unwrap_response_data(self, payload: Any) -> dict[str, Any] | None:
        """兼容后端标准响应包裹和 worker 裸响应。"""
        if not isinstance(payload, dict):
            return None
        if "code" in payload and "data" in payload:
            data = payload.get("data")
            return data if isinstance(data, dict) else None
        return payload

    def _parse_case_run_snapshot(self, data: dict[str, Any]) -> Any:
        """解析用例运行快照"""
        from ..contracts.types import (
            UiBrowserOptionsSnapshot,
            UiBrowserViewport,
            UiCaseRunSnapshot,
            UiCaseSnapshot,
            UiRunOptionsSnapshot,
            UiStepDefinition,
            UiSuiteSnapshot,
        )

        case_data = data.get("case", {})
        steps = None
        if "steps" in case_data and case_data["steps"]:
            steps = [
                UiStepDefinition(
                    keyword=s.get("keyword", ""),
                    order_no=s.get("orderNo"),
                    step_name=s.get("stepName"),
                    locator_type=s.get("locatorType"),
                    locator_value=s.get("locatorValue"),
                    operation_value=s.get("operationValue"),
                    expect_value=s.get("expectValue"),
                    timeout_ms=s.get("timeoutMs"),
                    continue_on_failure=s.get("continueOnFailure"),
                    enabled=s.get("enabled"),
                    description=s.get("description"),
                    comparator=s.get("comparator"),
                )
                for s in case_data["steps"]
            ]

        case = UiCaseSnapshot(
            case_id=case_data.get("caseId", ""),
            name=case_data.get("name", ""),
            suite_id=case_data.get("suiteId"),
            description=case_data.get("description"),
            enabled=case_data.get("enabled"),
            order_no=case_data.get("orderNo"),
            steps_json=case_data.get("stepsJson"),
            steps=steps,
        )

        suite = None
        if "suite" in data and data["suite"]:
            suite_data = data["suite"]
            suite = UiSuiteSnapshot(
                suite_id=suite_data.get("suiteId", ""),
                name=suite_data.get("name", ""),
                headless=suite_data.get("headless"),
                slow_mo_ms=suite_data.get("slowMoMs"),
                viewport_width=suite_data.get("viewportWidth"),
                viewport_height=suite_data.get("viewportHeight"),
                default_step_timeout_ms=suite_data.get("defaultStepTimeoutMs"),
                screenshot_policy=suite_data.get("screenshotPolicy", "on_failure"),
            )

        browser = None
        if "browser" in data and data["browser"]:
            browser_data = data["browser"]
            viewport = None
            if "viewport" in browser_data and browser_data["viewport"]:
                viewport = UiBrowserViewport(
                    width=browser_data["viewport"].get("width", 1280),
                    height=browser_data["viewport"].get("height", 720),
                )
            browser = UiBrowserOptionsSnapshot(
                headless=browser_data.get("headless"),
                slow_mo_ms=browser_data.get("slowMoMs"),
                viewport=viewport,
            )

        options = None
        if "options" in data and data["options"]:
            options_data = data["options"]
            options = UiRunOptionsSnapshot(
                default_step_timeout_ms=options_data.get("defaultStepTimeoutMs"),
            )

        return UiCaseRunSnapshot(
            task_id=data.get("taskId", ""),
            run_id=data.get("runId", ""),
            case=case,
            suite=suite,
            browser=browser,
            options=options,
        )

    def _parse_suite_run_snapshot(self, data: dict[str, Any]) -> Any:
        """解析测试集运行快照"""
        from ..contracts.types import (
            UiBrowserOptionsSnapshot,
            UiBrowserViewport,
            UiCaseSnapshot,
            UiRunOptionsSnapshot,
            UiStepDefinition,
            UiSuiteRunItemSnapshot,
            UiSuiteSnapshot,
            UiTestSuiteRunSnapshot,
        )

        items = []
        for item_data in data.get("items", []):
            case_data = item_data.get("case", {})
            steps = None
            if "steps" in case_data and case_data["steps"]:
                steps = [
                    UiStepDefinition(
                        keyword=s.get("keyword", ""),
                        order_no=s.get("orderNo"),
                        step_name=s.get("stepName"),
                        locator_type=s.get("locatorType"),
                        locator_value=s.get("locatorValue"),
                        operation_value=s.get("operationValue"),
                        expect_value=s.get("expectValue"),
                        timeout_ms=s.get("timeoutMs"),
                        continue_on_failure=s.get("continueOnFailure"),
                        enabled=s.get("enabled"),
                        description=s.get("description"),
                        comparator=s.get("comparator"),
                    )
                    for s in case_data["steps"]
                ]

            case = UiCaseSnapshot(
                case_id=case_data.get("caseId", ""),
                name=case_data.get("name", ""),
                suite_id=case_data.get("suiteId"),
                description=case_data.get("description"),
                enabled=case_data.get("enabled"),
                order_no=case_data.get("orderNo"),
                steps_json=case_data.get("stepsJson"),
                steps=steps,
            )

            items.append(UiSuiteRunItemSnapshot(
                item_id=item_data.get("itemId", ""),
                continue_on_failure=item_data.get("continueOnFailure", False),
                case=case,
            ))

        suite = None
        if "suite" in data and data["suite"]:
            suite_data = data["suite"]
            suite = UiSuiteSnapshot(
                suite_id=suite_data.get("suiteId", ""),
                name=suite_data.get("name", ""),
                headless=suite_data.get("headless"),
                slow_mo_ms=suite_data.get("slowMoMs"),
                viewport_width=suite_data.get("viewportWidth"),
                viewport_height=suite_data.get("viewportHeight"),
                default_step_timeout_ms=suite_data.get("defaultStepTimeoutMs"),
                screenshot_policy=suite_data.get("screenshotPolicy", "on_failure"),
            )

        browser = None
        if "browser" in data and data["browser"]:
            browser_data = data["browser"]
            viewport = None
            if "viewport" in browser_data and browser_data["viewport"]:
                viewport = UiBrowserViewport(
                    width=browser_data["viewport"].get("width", 1280),
                    height=browser_data["viewport"].get("height", 720),
                )
            browser = UiBrowserOptionsSnapshot(
                headless=browser_data.get("headless"),
                slow_mo_ms=browser_data.get("slowMoMs"),
                viewport=viewport,
            )

        options = None
        if "options" in data and data["options"]:
            options_data = data["options"]
            options = UiRunOptionsSnapshot(
                default_step_timeout_ms=options_data.get("defaultStepTimeoutMs"),
            )

        return UiTestSuiteRunSnapshot(
            task_id=data.get("taskId", ""),
            run_id=data.get("runId", ""),
            items=items,
            suite=suite,
            browser=browser,
            options=options,
        )

    def _serialize_task_result(self, payload: UiCaseRunResult | UiSuiteRunResult) -> dict[str, Any]:
        """序列化任务结果"""
        result = asdict(payload)
        # 转换字段名为驼峰命名
        return self._to_camel_case(result)

    def _serialize_suite_item_result(self, payload: UiSuiteItemRunResult) -> dict[str, Any]:
        """序列化测试集项结果"""
        result = asdict(payload)
        return self._to_camel_case(result)

    def _to_camel_case(self, data: dict[str, Any]) -> dict[str, Any]:
        """将下划线命名转换为驼峰命名"""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key == "screenshot_path" and isinstance(value, str):
                value = build_artifact_url(
                    value,
                    self._config.artifacts_root_dir,
                    self._config.artifacts_base_url,
                )

            # 转换 key
            parts = key.split("_")
            camel_key = parts[0] + "".join(p.capitalize() for p in parts[1:])

            # 递归转换嵌套的字典
            if isinstance(value, dict):
                result[camel_key] = self._to_camel_case(value)
            # 递归转换列表中的字典
            elif isinstance(value, list):
                result[camel_key] = [
                    self._to_camel_case(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[camel_key] = value

        return result


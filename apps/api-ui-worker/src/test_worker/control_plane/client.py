"""控制面客户端：领取任务、读取快照、上报进度与结果。"""

from __future__ import annotations

import re
import time
from dataclasses import asdict
from typing import Any
from types import NotImplementedType
from urllib.parse import urlencode

import httpx

from .artifacts import ArtifactUploader
from ..contracts.parsing import parse_snapshot_response, parse_ui_task
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


CONTROL_PLANE_ROUTE_LIMIT = 200
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_SAFE_STATUS_DETAILS = {
    0: "no response",
    400: "bad request",
    401: "unauthorized",
    403: "forbidden",
    404: "not found",
    405: "method not allowed",
    409: "conflict",
    410: "gone",
    422: "validation failed",
    429: "rate limited",
}


def _safe_route(pathname: str) -> str:
    route = pathname.split("?", 1)[0].strip()
    if not route:
        return "/"
    return route[:CONTROL_PLANE_ROUTE_LIMIT]


def _status_detail(status_code: int) -> str:
    if status_code in _SAFE_STATUS_DETAILS:
        return _SAFE_STATUS_DETAILS[status_code]
    return "server error" if status_code >= 500 else "request rejected"


def _safe_error_code(response: httpx.Response) -> str:
    """Extract only a token-shaped error code; never retain the response body."""
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    code = payload.get("code")
    if isinstance(code, bool):
        return ""
    if isinstance(code, int):
        code = str(code)
    if not isinstance(code, str):
        return ""
    code = code.strip()
    return code if _SAFE_ERROR_CODE.fullmatch(code) else ""


class ControlPlaneRequestError(Exception):
    """Control-plane HTTP failure with a fixed, body-free message."""

    def __init__(
        self,
        method: str,
        pathname: str,
        status_code: int,
        error_code: str = "",
    ) -> None:
        self.method = method.upper()
        self.pathname = _safe_route(pathname)
        self.status_code = status_code
        self.error_code = error_code if _SAFE_ERROR_CODE.fullmatch(error_code) else ""
        message = (
            f"control plane request failed: {self.method} {self.pathname} -> "
            f"{status_code} {_status_detail(status_code)}"
        )
        if self.error_code:
            message += f" (code={self.error_code})"
        super().__init__(message)


# The control plane answers with one of these only when this worker no longer holds
# the execution: the lease expired or was taken over, the task or run is gone, or the
# worker token is no longer accepted. A 400 or 422 means the request itself is wrong.
LEASE_LOST_STATUSES = frozenset({401, 403, 404, 409, 410})


class ExecutionLeaseLost(Exception):
    """This worker's execution authority ended; ``status_code`` is None for a local expiry."""

    def __init__(self, status_code: int | None = None) -> None:
        super().__init__("执行租约已失效")
        self.status_code = status_code


def lease_rejection_status(error: Exception) -> int | None:
    """The status of the control plane's rejection of this execution, if that is ``error``."""
    if (
        isinstance(error, ControlPlaneRequestError)
        and error.status_code in LEASE_LOST_STATUSES
    ):
        return error.status_code
    return None


def raise_if_lease_lost(error: Exception) -> None:
    """Report the control plane's rejection of this execution as ``ExecutionLeaseLost``."""
    status = lease_rejection_status(error)
    if status is not None:
        raise ExecutionLeaseLost(status) from None


class ControlPlaneClient:
    """控制面客户端类"""

    def __init__(self, config: WorkerConfig) -> None:
        """
        初始化控制面客户端

        Args:
            config: 工作配置
        """
        self._config = config
        self._artifacts = ArtifactUploader(config, self._request)
        self._client = httpx.Client(
            base_url=config.control_plane_base_url.rstrip("/"),
            headers={
                "Content-Type": "application/json",
                "X-Worker-Token": config.worker_token,
            },
            timeout=config.request_timeout_ms / 1000,
        )

    def claim_next_task(self) -> dict[str, Any] | None | NotImplementedType:
        """Claim the globally oldest task; ``NotImplemented`` means an older server."""
        pathname = "/internal/api-worker/tasks/claim-next"
        try:
            return self._request("POST", pathname, {"workerId": self._config.worker_id})
        except ControlPlaneRequestError as error:
            if error.status_code == 404:
                return NotImplemented
            raise

    def claim_task(self) -> UiWorkerTask | None:
        """
        领取任务

        Returns:
            任务对象，如果没有可用任务则返回 None
        """
        data = self._request(
            "POST",
            "/internal/ui-worker/tasks/claim",
            {
                "workerId": self._config.worker_id,
            },
        )
        if data is None:
            return None
        return parse_ui_task(data)

    def claim_api_task(self) -> dict[str, Any] | None:
        """领取 API worker 任务。"""
        data = self._request(
            "POST",
            "/internal/api-worker/tasks/claim",
            {
                "workerId": self._config.worker_id,
            },
        )
        return data

    def task_stop_requested(self, domain: str, task_id: str) -> bool:
        """Check persistent stop intent for the current worker lease."""
        query = urlencode({"worker_id": self._config.worker_id})
        result = self._request(
            "GET",
            f"/internal/{domain}-worker/tasks/{task_id}/control?{query}",
            timeout=3,
        )
        return bool(result and result.get("stopRequested"))

    def get_api_task_snapshot(self, task_id: str) -> dict[str, Any]:
        """获取 API worker 任务快照。"""
        data = self._request("GET", f"/internal/api-worker/tasks/{task_id}/snapshot")
        if data is None:
            raise ValueError(f"api task {task_id} snapshot is empty")
        return data

    def report_api_task_started(self, task_id: str, started_at: str) -> None:
        """上报 API 任务开始。"""
        self._request(
            "POST",
            f"/internal/api-worker/tasks/{task_id}/started",
            {
                "workerId": self._config.worker_id,
                "startedAt": started_at,
            },
        )

    def report_api_task_heartbeat(self, task_id: str, heartbeat_at: str) -> None:
        """上报 API 任务心跳。"""
        self._request(
            "POST",
            f"/internal/api-worker/tasks/{task_id}/heartbeat",
            {
                "workerId": self._config.worker_id,
                "heartbeatAt": heartbeat_at,
            },
        )

    def report_api_collection_item_started(
        self, task_id: str, item_id: str, payload: dict[str, Any]
    ) -> None:
        """上报 API collection item 开始。"""
        body = {
            "workerId": self._config.worker_id,
            **payload,
        }
        self._request(
            "POST",
            f"/internal/api-worker/tasks/{task_id}/collection-items/{item_id}/started",
            body,
        )

    def report_api_collection_item_completed(
        self, task_id: str, item_id: str, payload: dict[str, Any]
    ) -> None:
        """上报 API collection item 完成。"""
        body = {
            "workerId": self._config.worker_id,
            **payload,
        }
        self._request(
            "POST",
            f"/internal/api-worker/tasks/{task_id}/collection-items/{item_id}/completed",
            body,
        )

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

        return parse_snapshot_response(
            data,
            default_task_id=task_id,
            default_screenshot_policy="on_failure",
        )

    def resolve_ui_run_variables(
        self, task_id: str, run_id: str, names: list[str]
    ) -> dict[str, Any]:
        """
        获取本次运行环境下指定变量的当前取值。

        Args:
            task_id: 当前任务 ID
            run_id: 用例运行或套件运行的业务标识
            names: 需要解析的变量名

        Returns:
            包含 values 与 missing 的响应
        """
        data = self._request(
            "POST",
            f"/internal/ui-runs/{run_id}/variables:resolve",
            {
                "taskId": task_id,
                "workerId": self._config.worker_id,
                "names": list(names),
            },
            timeout=5.0,
            retries=1,
        )
        return data or {}

    def write_ui_run_variables(
        self, task_id: str, run_id: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        把后置提取的结果立即写回运行环境。

        Args:
            task_id: 当前任务 ID
            run_id: 用例运行或套件运行的业务标识
            items: name / value / orderNo 列表

        Returns:
            包含 results 的响应
        """
        data = self._request(
            "POST",
            f"/internal/ui-runs/{run_id}/variables:write",
            {
                "taskId": task_id,
                "workerId": self._config.worker_id,
                "items": list(items),
            },
            timeout=5.0,
            retries=1,
        )
        return data or {}

    def report_task_started(self, task_id: str, payload: UiTaskStartedPayload) -> None:
        """
        上报任务开始

        Args:
            task_id: 任务 ID
            payload: 开始负载
        """
        self._request(
            "POST",
            f"/internal/ui-worker/tasks/{task_id}/started",
            self._serialize(payload),
        )

    def report_task_heartbeat(
        self, task_id: str, payload: UiTaskHeartbeatPayload
    ) -> None:
        """
        上报心跳

        Args:
            task_id: 任务 ID
            payload: 心跳负载
        """
        self._request(
            "POST",
            f"/internal/ui-worker/tasks/{task_id}/heartbeat",
            self._serialize(payload),
        )

    def report_ui_steps(
        self, task_id: str, item_id: str | None, steps: list[dict[str, Any]]
    ) -> None:
        """Publish a snapshot of UI progress, with verified artifact references."""
        path = f"/internal/ui-worker/tasks/{task_id}"
        if item_id is not None:
            path += f"/suite-items/{item_id}"
        body = self._to_camel_case({"step_results": steps})
        body = self._artifacts.publish(task_id, body)
        self._request(
            "POST",
            path + "/steps",
            {"workerId": self._config.worker_id, **body},
            timeout=3,
        )

    def report_suite_item_started(
        self, task_id: str, item_id: str, payload: UiSuiteItemStartedPayload
    ) -> None:
        """
        上报测试集项开始

        Args:
            task_id: 任务 ID
            item_id: 测试集项 ID
            payload: 开始负载
        """
        body = {
            "workerId": self._config.worker_id,
            **self._serialize(payload),
        }
        self._request(
            "POST",
            f"/internal/ui-worker/tasks/{task_id}/suite-items/{item_id}/started",
            body,
        )

    def report_suite_item_completed(
        self, task_id: str, item_id: str, payload: UiSuiteItemRunResult
    ) -> None:
        """
        上报测试集项完成

        Args:
            task_id: 任务 ID
            item_id: 测试集项 ID
            payload: 完成负载
        """
        body = {
            "workerId": self._config.worker_id,
            **self._artifacts.publish(task_id, self._serialize(payload)),
        }
        self._request(
            "POST",
            f"/internal/ui-worker/tasks/{task_id}/suite-items/{item_id}/completed",
            body,
        )

    def report_task_completed(
        self, task_id: str, payload: UiCaseRunResult | UiSuiteRunResult
    ) -> None:
        """
        上报任务完成

        Args:
            task_id: 任务 ID
            payload: 完成负载
        """
        body = {
            "workerId": self._config.worker_id,
            **self._artifacts.publish(task_id, self._serialize(payload)),
        }
        self._request(
            "POST", f"/internal/ui-worker/tasks/{task_id}/completed", body, timeout=300
        )
        self._artifacts.cleanup(task_id)

    def _request(
        self,
        method: str,
        pathname: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
        retries: int = 0,
    ) -> dict[str, Any] | None:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            pathname: 请求路径
            body: 请求体
            timeout: 本次请求超时秒数，缺省使用客户端配置
            retries: 传输失败或 5xx 时的重试次数

        Returns:
            响应数据，如果状态码为 204 则返回 None

        Raises:
            ControlPlaneRequestError: 控制面返回错误状态或连接失败时抛出
        """
        attempt = 0
        while True:
            try:
                kwargs: dict[str, Any] = {}
                if body is not None:
                    kwargs["json"] = body
                if timeout is not None:
                    kwargs["timeout"] = timeout
                response = self._client.request(method, pathname, **kwargs)

                if response.status_code == 204:
                    return None

                response.raise_for_status()

                if not response.content:
                    return None

                return self._unwrap_response_data(response.json())
            except httpx.HTTPStatusError as e:
                if attempt < retries and e.response.status_code >= 500:
                    attempt += 1
                    time.sleep(0.2)
                    continue
                raise ControlPlaneRequestError(
                    method,
                    pathname,
                    e.response.status_code,
                    _safe_error_code(e.response),
                ) from e
            except Exception as e:
                if attempt < retries:
                    attempt += 1
                    time.sleep(0.2)
                    continue
                # No status exists, and the exception text may quote a URL or request line.
                raise ControlPlaneRequestError(method, pathname, 0) from e

    def _unwrap_response_data(self, payload: Any) -> dict[str, Any] | None:
        """兼容后端标准响应包裹和 worker 裸响应。"""
        if not isinstance(payload, dict):
            return None
        if "code" in payload and "data" in payload:
            data = payload.get("data")
            return data if isinstance(data, dict) else None
        return payload

    def _serialize(self, payload: Any) -> dict[str, Any]:
        """把负载数据类序列化为驼峰键的字典"""
        return self._to_camel_case(asdict(payload))

    def _to_camel_case(self, data: dict[str, Any]) -> dict[str, Any]:
        """将下划线命名转换为驼峰命名"""
        result: dict[str, Any] = {}
        for key, value in data.items():
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

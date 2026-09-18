"""
类型定义模块
定义所有 UI 测试 worker 使用的数据类型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# 工作模式类型
WorkerMode = Literal["poll", "once"]

# 任务类型
UiTaskType = Literal["case_debug", "suite_run"]

# 步骤状态
UiStepStatus = Literal["success", "failed", "error", "skipped"]

# 用例运行状态
UiCaseRunStatus = Literal["success", "failed", "error"]

# 测试集项运行状态
UiSuiteItemRunStatus = Literal["success", "failed", "error", "skipped"]

# 测试集运行状态
UiSuiteRunStatus = Literal["success", "failed", "error", "canceled"]

# 比较器类型
ComparatorType = Literal["eq", "contains"]

# 截图策略
ScreenshotPolicy = Literal["on_failure", "after_each_step", "never"]


@dataclass
class WorkerConfig:
    """工作配置"""
    mode: WorkerMode
    worker_id: str
    control_plane_base_url: str
    worker_token: str
    poll_interval_ms: int
    request_timeout_ms: int
    heartbeat_interval_ms: int
    artifacts_root_dir: str
    default_headless: bool
    default_slow_mo_ms: int
    trace_enabled: bool
    screenshot_on_failure: bool
    snapshot_file: str
    artifacts_bind_host: str = "127.0.0.1"
    artifacts_port: int = 9010
    artifacts_base_url: str = ""


@dataclass
class UiWorkerTask:
    """UI 工作任务"""
    task_id: str
    task_type: UiTaskType
    run_id: str
    suite_id: str = ""
    case_id: str = ""
    lease_seconds: int = 0


@dataclass
class UiBrowserViewport:
    """浏览器视口"""
    width: int
    height: int


@dataclass
class UiBrowserOptionsSnapshot:
    """浏览器选项快照"""
    headless: bool | None = None
    slow_mo_ms: int | None = None
    viewport: UiBrowserViewport | None = None


@dataclass
class UiRunOptionsSnapshot:
    """运行选项快照"""
    default_step_timeout_ms: int | None = None


@dataclass
class UiSuiteSnapshot:
    """测试套件快照"""
    suite_id: str
    name: str
    headless: bool | None = None
    slow_mo_ms: int | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    default_step_timeout_ms: int | None = None
    screenshot_policy: ScreenshotPolicy | None = None


@dataclass
class UiStepDefinition:
    """步骤定义"""
    keyword: str
    order_no: int | None = None
    step_name: str | None = None
    locator_type: str | None = None
    locator_value: str | None = None
    operation_value: str | None = None
    expect_value: str | None = None
    timeout_ms: int | None = None
    continue_on_failure: bool | None = None
    enabled: bool | None = None
    description: str | None = None
    comparator: ComparatorType | None = None


@dataclass
class UiCaseSnapshot:
    """用例快照"""
    case_id: str
    name: str
    suite_id: str | None = None
    description: str | None = None
    enabled: bool | None = None
    order_no: int | None = None
    steps_json: list[dict[str, Any]] | None = None
    steps: list[UiStepDefinition] | None = None


@dataclass
class UiCaseRunSnapshot:
    """用例运行快照"""
    task_id: str
    run_id: str
    case: UiCaseSnapshot
    suite: UiSuiteSnapshot | None = None
    browser: UiBrowserOptionsSnapshot | None = None
    options: UiRunOptionsSnapshot | None = None


@dataclass
class UiSuiteRunItemSnapshot:
    """测试集运行项快照"""
    item_id: str
    continue_on_failure: bool
    case: UiCaseSnapshot


@dataclass
class UiTestSuiteRunSnapshot:
    """测试集运行快照"""
    task_id: str
    run_id: str
    items: list[UiSuiteRunItemSnapshot]
    suite: UiSuiteSnapshot | None = None
    browser: UiBrowserOptionsSnapshot | None = None
    options: UiRunOptionsSnapshot | None = None


@dataclass
class UiWorkerTaskSnapshotResponse:
    """任务快照响应"""
    task_type: UiTaskType
    case_run: UiCaseRunSnapshot | None = None
    suite_run: UiTestSuiteRunSnapshot | None = None


@dataclass
class UiStepRunResult:
    """步骤运行结果"""
    order_no: int
    step_name: str
    keyword: str
    status: UiStepStatus
    success: bool
    started_at: str
    finished_at: str
    duration_ms: int
    actual_value: str | None = None
    screenshot_path: str | None = None
    error_message: str | None = None


@dataclass
class UiCaseRunResult:
    """用例运行结果"""
    task_id: str
    run_id: str
    case_id: str
    status: UiCaseRunStatus
    success: bool
    started_at: str
    finished_at: str
    duration_ms: int
    step_results: list[UiStepRunResult] = field(default_factory=list)
    current_url: str | None = None
    trace_path: str | None = None
    error_message: str | None = None


@dataclass
class UiSuiteItemRunResult:
    """测试集项运行结果"""
    item_id: str
    run_id: str
    case_id: str
    status: UiSuiteItemRunStatus
    success: bool
    finished_at: str
    duration_ms: int
    step_results: list[UiStepRunResult] = field(default_factory=list)
    started_at: str | None = None
    current_url: str | None = None
    error_message: str | None = None


@dataclass
class UiSuiteRunResult:
    """测试集运行结果"""
    task_id: str
    run_id: str
    suite_id: str
    status: UiSuiteRunStatus
    success: bool
    started_at: str
    finished_at: str
    duration_ms: int
    current_url: str | None = None
    trace_path: str | None = None
    error_message: str | None = None


@dataclass
class UiTaskStartedPayload:
    """任务开始上报负载"""
    worker_id: str
    started_at: str


@dataclass
class UiTaskHeartbeatPayload:
    """心跳上报负载"""
    worker_id: str
    heartbeat_at: str


@dataclass
class UiSuiteItemStartedPayload:
    """测试集项开始上报负载"""
    run_id: str
    case_id: str
    started_at: str



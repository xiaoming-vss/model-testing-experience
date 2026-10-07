"""状态值域枚举。

各实体状态机的取值集中定义,值字符串与历史/Go worker 契约逐字一致,
仅做赋值与比较的收敛,不改变任何落库值。
"""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    """运行记录状态:worker_tasks 与 api/ui run 表共用。"""

    PENDING = "pending"
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    CANCELED = "canceled"
    SKIPPED = "skipped"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class SprintStatus(StrEnum):
    """迭代状态。"""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"


class BugStatus(StrEnum):
    """禅道主状态；确认情况和解决方案独立保存。"""

    ACTIVE = "active"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


# 已解决（包括延期处理）仍未关闭。
BUG_UNCLOSED_STATUSES = frozenset({BugStatus.ACTIVE.value, BugStatus.RESOLVED.value})


class BugResolution(StrEnum):
    BY_DESIGN = "bydesign"
    DUPLICATE = "duplicate"
    EXTERNAL = "external"
    FIXED = "fixed"
    NOT_REPRODUCIBLE = "notrepro"
    POSTPONED = "postponed"
    WILL_NOT_FIX = "willnotfix"
    TO_STORY = "tostory"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class BugSeverity(StrEnum):
    """Bug 严重程度。"""

    FATAL = "fatal"
    SERIOUS = "serious"
    NORMAL = "normal"
    MINOR = "minor"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class BugPriority(StrEnum):
    """Bug 处理优先级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class BugRejectReason(StrEnum):
    """拒绝原因：必须三选一，允许补充说明。"""

    BY_DESIGN = "by_design"
    NOT_REPRODUCIBLE = "not_reproducible"
    DEFERRED = "deferred"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class BugAction(StrEnum):
    """Bug 状态流转动作；合法的 (当前状态, 动作) 组合由服务层流转表定义。"""

    CONFIRM = "confirm"
    RESOLVE = "resolve"
    CLOSE = "close"
    ACTIVATE = "activate"
    # 旧客户端动作兼容；新页面使用以上四种动作。
    REJECT = "reject"
    SUBMIT_FIX = "submit_fix"
    REGRESSION_PASS = "regression_pass"
    REGRESSION_FAIL = "regression_fail"
    REOPEN = "reopen"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class BugActivityKind(StrEnum):
    """Bug 动态类型：处理记录取 status_change，评论与动态取其余类型。"""

    STATUS_CHANGE = "status_change"
    TRANSFER = "transfer"
    COMMENT = "comment"
    EDIT = "edit"
    ATTACHMENT = "attachment"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class ConnectionStatus(StrEnum):
    """集成连接状态。"""

    ACTIVE = "active"
    AUTH_FAILED = "auth_failed"


class BindingStatus(StrEnum):
    """资源绑定状态。"""

    ACTIVE = "active"
    UNBOUND = "unbound"


class ReviewStatus(StrEnum):
    """AI 生成结果审查状态。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ImportStatus(StrEnum):
    """AI 生成结果导入状态。"""

    PENDING = "pending"
    IMPORTED = "imported"
    SAVED = "saved"
    RETRYING = "retrying"


class StageStatus(StrEnum):
    """AI 生成任务阶段状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_REVIEW = "waiting_review"
    EMPTY = ""

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class TestOrderStatus(StrEnum):
    """测试单状态：由条目状态推导，不是人工关闭事件。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TestOrderEntryStatus(StrEnum):
    """执行条目状态：一次执行的结论。"""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


# 成功语义兼容集合:历史/Go 侧可能传 passed/completed,统一视为成功。
SUCCESS_STATUSES = {RunStatus.SUCCESS.value, "passed", "completed"}

# 仍在推进中的运行记录:worker 可能还会写回结果,不允许删除。
RUN_ACTIVE_STATUSES = {
    RunStatus.PENDING.value,
    RunStatus.QUEUED.value,
    RunStatus.CLAIMED.value,
    RunStatus.RUNNING.value,
}

# 执行条目的终态:到达其中之一即视为本条已执行完。
TEST_ORDER_ENTRY_TERMINAL_STATUSES = {
    TestOrderEntryStatus.PASSED.value,
    TestOrderEntryStatus.FAILED.value,
    TestOrderEntryStatus.BLOCKED.value,
    TestOrderEntryStatus.SKIPPED.value,
}

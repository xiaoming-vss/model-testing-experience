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


# 成功语义兼容集合:历史/Go 侧可能传 passed/completed,统一视为成功。
SUCCESS_STATUSES = {RunStatus.SUCCESS.value, "passed", "completed"}

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class TestOrderEntry(Base):
    """执行条目：测试单里被执行的一条用例，保存加入时的用例内容快照。"""

    __tablename__ = "test_order_entries"
    __table_args__ = (
        UniqueConstraint("order_id", "case_type", "case_id", name="uk_test_order_entry_case"),
        Index("idx_test_order_entry_order", "order_id", "order_no"),
        Index("idx_order_entry_status_page", "order_id", "status", "order_no", "id"),
        Index("idx_order_entry_assignee_page", "order_id", "assignee_user_id", "order_no", "id"),
        {"comment": "测试单执行条目；保存选入时用例快照、执行人分配及人工结论"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    entry_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="测试单执行条目业务标识"
    )
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "test_orders.order_id",
            name="fk_test_order_entries_order_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
        comment="测试单业务标识",
    )
    # 条目按「用例类型 + 用例 ID」引用，为 API/UI 用例留位；用例被删除时由删除服务清理条目。
    case_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="function",
        comment="引用用例类型；当前手工执行使用 function",
    )
    case_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="测试用例业务标识"
    )
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    step_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="冻结用例快照中的步骤条数；供摘要列表展示，随快照创建后保持不变",
    )
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: {"preconditions": [], "steps": []},
        comment="加入测试单时冻结的功能用例内容 JSON",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="pending",
        comment="人工执行状态：pending/passed/failed/blocked/skipped",
    )
    # 分配执行人：空串表示未分配；仅项目所有者可分配与改派。
    assignee_user_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        default="",
        comment="分配的执行人用户业务标识；空字符串表示未分配",
    )
    # 执行结果：整条用例的结论与实际结果，执行人在判定时写入。
    actual_results: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="人工执行实际结果"
    )
    failure_reason: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="人工执行失败原因"
    )
    block_reason: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="人工执行阻塞原因"
    )
    zentao_bug_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="关联禅道缺陷编号，区别于平台 Bug 业务标识"
    )
    executor_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="实际执行人用户业务标识"
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="人工执行判定时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

    # 响应派生字段：不落库，来自被引用用例的当前身份。
    case_title = ""
    case_module = ""
    case_priority = ""
    requirement_id = ""
    requirement_name = ""

    def __init__(self, **kwargs: Any) -> None:
        snapshot = kwargs.get("snapshot_json")
        steps = snapshot.get("steps", []) if isinstance(snapshot, dict) else []
        kwargs.setdefault("step_count", len(steps) if isinstance(steps, list) else 0)
        super().__init__(**kwargs)

    @property
    def snapshot(self) -> dict[str, Any]:
        return self.snapshot_json or {}

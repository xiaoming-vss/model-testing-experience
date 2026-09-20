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
    )
    id: Mapped[IdPk]
    entry_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "test_orders.order_id",
            name="fk_test_order_entries_order_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    # 条目按「用例类型 + 用例 ID」引用，为 API/UI 用例留位；用例被删除时由删除服务清理条目。
    case_type: Mapped[str] = mapped_column(String(20), nullable=False, default="function")
    case_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: {"preconditions": [], "steps": []}
    )
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    # 分配执行人：空串表示未分配；仅项目所有者可分配与改派。
    assignee_user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, default=""
    )
    # 执行结果：整条用例的结论与实际结果，执行人在判定时写入。
    actual_results: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    failure_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    block_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    zentao_bug_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    executor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # 响应派生字段：不落库，来自被引用用例的当前身份。
    case_title = ""
    case_module = ""
    case_priority = ""

    @property
    def snapshot(self) -> dict[str, Any]:
        return self.snapshot_json or {}

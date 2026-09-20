from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class TestOrder(Base):
    """手工测试单：一次执行的组织单位，归属一个项目与一个迭代。"""

    __tablename__ = "test_orders"
    __table_args__ = (UniqueConstraint("sprint_id", "name", name="uk_test_order_sprint_name"),)
    id: Mapped[IdPk]
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_test_orders_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    sprint_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sprints.sprint_id", name="fk_test_orders_sprint_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tested_version: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # 响应派生字段：不落库，由条目状态推导（与迭代状态同样是推导值，不代表人工关闭）。
    entries_total = 0
    entries_executed = 0
    entries_passed = 0
    entries_failed = 0
    entries_blocked = 0
    entries_skipped = 0
    status = ""

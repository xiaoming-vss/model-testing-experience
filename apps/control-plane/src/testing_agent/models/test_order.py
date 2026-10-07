from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class TestOrder(Base):
    """手工测试单：一次执行的组织单位，归属一个项目与一个迭代。"""

    __tablename__ = "test_orders"
    __table_args__ = (
        UniqueConstraint("sprint_id", "name", name="uk_test_order_sprint_name"),
        {"comment": "项目迭代中的一次手工测试执行；多轮执行通过新建测试单表达"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    order_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="测试单业务标识"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_test_orders_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
        comment="项目业务标识",
    )
    sprint_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sprints.sprint_id", name="fk_test_orders_sprint_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
        comment="迭代业务标识",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    tested_version: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="本次手工测试的被测版本"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

    # 响应派生字段：不落库，由条目状态推导（与迭代状态同样是推导值，不代表人工关闭）。
    entries_total = 0
    entries_executed = 0
    entries_passed = 0
    entries_failed = 0
    entries_blocked = 0
    entries_skipped = 0
    status = ""

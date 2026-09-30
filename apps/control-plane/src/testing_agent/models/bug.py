from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class Bug(Base):
    """平台内 Bug：项目内自增编号，发现迭代与计划修复迭代分离。

    迭代与需求按业务键引用、不建外键：Bug 是跨迭代长期存在的记录，
    迭代或需求被删除时 Bug 保留引用值，展示层回退为「未关联」。
    执行来源（测试单/条目/用例）同样只存业务键加建时快照名称。
    """

    __tablename__ = "bugs"
    __table_args__ = (UniqueConstraint("project_id", "bug_no", name="uk_bugs_project_bug_no"),)
    id: Mapped[IdPk]
    bug_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    bug_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_bugs_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description_html: Mapped[str] = mapped_column(LONGTEXT, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="pending")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    # 创建人保留最初提交人，不随转派变化；责任人可独立转派。
    reporter_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    assignee_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    found_sprint_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    planned_fix_sprint_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_order_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_entry_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="")
    source_case_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_order_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    source_case_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # 响应派生字段：不落库，来自所属需求的当前名称。
    requirement_name = ""

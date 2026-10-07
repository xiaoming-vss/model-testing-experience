from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
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
    __table_args__ = (
        Index("idx_bug_project_created", "project_id", "created_at", "id"),
        UniqueConstraint("project_id", "bug_no", name="uk_bugs_project_bug_no"),
        {"comment": "平台 Bug 及当前处理状态；激活、解决、关闭与确认、解决方案独立保存"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    bug_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="平台 Bug 业务标识"
    )
    bug_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="项目内唯一 Bug 序号，展示为 BUG-序号"
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.project_id", name="fk_bugs_project_id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
        comment="项目业务标识",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")
    description_html: Mapped[str] = mapped_column(
        LONGTEXT, nullable=False, default="", comment="Bug 富文本正文 HTML"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="active",
        comment="Bug 主状态：active/resolved/closed",
    )
    confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="Bug 是否已确认"
    )
    resolution: Mapped[str] = mapped_column(
        String(20),
        default="",
        server_default="",
        comment="解决方案：fixed/bydesign/duplicate/external/notrepro/postponed/willnotfix/tostory",
    )
    resolved_build: Mapped[str] = mapped_column(
        String(255), default="", server_default="", comment="Bug 解决版本"
    )
    duplicate_bug: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="重复目标的平台 Bug 数据库主键（bugs.id）；0 表示无重复关联",
    )
    activated_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="Bug 重新激活累计次数"
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal", comment="Bug 严重程度"
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", comment="优先级"
    )
    # 创建人保留最初提交人，不随转派变化；责任人可独立转派。
    reporter_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="Bug 报告人用户业务标识"
    )
    assignee_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="当前责任人用户业务标识"
    )
    found_sprint_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="发现 Bug 的迭代业务标识；来源删除后可保留引用",
    )
    planned_fix_sprint_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="计划修复迭代业务标识；来源删除后可保留引用"
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="关联需求业务标识；需求删除后可保留引用"
    )
    source_order_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        comment="Bug 来源测试单业务标识；来源删除后可保留引用",
    )
    source_entry_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        default="",
        comment="Bug 来源执行条目业务标识；来源删除后可保留引用",
    )
    source_case_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="Bug 来源用例业务标识；来源删除后可保留引用"
    )
    source_order_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="Bug 创建时的来源测试单名称快照"
    )
    source_case_title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="Bug 创建时的来源用例标题快照"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

    # 响应派生字段：不落库，来自所属需求的当前名称。
    requirement_name = ""

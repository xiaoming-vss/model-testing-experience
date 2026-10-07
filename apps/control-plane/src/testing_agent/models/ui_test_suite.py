from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiTestSuite(Base):
    __tablename__ = "ui_test_suites"
    __table_args__ = (
        UniqueConstraint("requirement_id", "name", name="uk_ui_suite_requirement_name"),
        {"comment": "需求下的 UI 测试套件及浏览器执行配置"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    suite_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="UI 测试套件业务标识"
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("requirements.requirement_id", name="fk_ui_test_suites_requirement"),
        nullable=False,
        comment="需求业务标识",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    description: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="业务描述"
    )
    headless: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="是否使用无头浏览器；空值时沿用 Worker 默认配置"
    )
    slow_mo_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="浏览器动作间延迟，单位毫秒；空值沿用默认配置"
    )
    viewport_width: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="浏览器视口宽度，单位像素；空值沿用默认配置"
    )
    viewport_height: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="浏览器视口高度，单位像素；空值沿用默认配置"
    )
    default_step_timeout_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="步骤默认超时，单位毫秒；空值沿用默认配置"
    )
    screenshot_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="on_failure", comment="截图策略"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

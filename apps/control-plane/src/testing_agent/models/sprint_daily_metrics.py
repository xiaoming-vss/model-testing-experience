from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class SprintDailyMetrics(Base):
    __tablename__ = "sprint_daily_metrics"
    __table_args__ = (
        UniqueConstraint("sprint_id", "snapshot_date", name="uk_sprint_date"),
        {"comment": "迭代每日指标快照；功能执行指标来自平台，缺陷指标来自禅道"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    project_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="项目业务标识"
    )
    sprint_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="迭代业务标识"
    )
    snapshot_date: Mapped[date] = mapped_column(
        Date, index=True, nullable=False, comment="指标快照对应的业务日期"
    )
    function_case_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="功能用例总数，按迭代快照口径统计"
    )
    function_case_executed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="功能用例已执行数，按迭代快照口径统计"
    )
    function_case_pending: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="功能用例待执行数，按迭代快照口径统计"
    )
    function_case_success: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="功能用例通过数，按迭代快照口径统计"
    )
    function_case_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="功能用例失败数，按迭代快照口径统计"
    )
    api_case_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="API用例总数，按迭代快照口径统计"
    )
    api_case_executed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="API用例已执行数，按迭代快照口径统计"
    )
    api_case_pending: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="API用例待执行数，按迭代快照口径统计"
    )
    api_case_success: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="API用例通过数，按迭代快照口径统计"
    )
    api_case_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="API用例失败数，按迭代快照口径统计"
    )
    ui_case_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="UI用例总数，按迭代快照口径统计"
    )
    ui_case_executed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="UI用例已执行数，按迭代快照口径统计"
    )
    ui_case_pending: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="UI用例待执行数，按迭代快照口径统计"
    )
    ui_case_success: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="UI用例通过数，按迭代快照口径统计"
    )
    ui_case_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="UI用例失败数，按迭代快照口径统计"
    )
    bug_metrics_collected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="本快照是否已成功统计缺陷；历史未采集为否"
    )
    bug_details_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "缺陷摘要快照 JSON；平台条目含 bugId/bugNo/title/status/severity/resolution，"
            "历史格式保留"
        ),
    )
    bug_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照总数"
    )
    bug_resolved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照已解决数"
    )
    bug_closed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照已关闭数"
    )
    bug_unresolved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照未解决数"
    )
    bug_fatal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照致命数"
    )
    bug_serious: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照严重数"
    )
    bug_normal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="缺陷快照一般数"
    )
    bug_suggestion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="缺陷快照轻微数；平台 minor 映射至历史 suggestion 字段",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

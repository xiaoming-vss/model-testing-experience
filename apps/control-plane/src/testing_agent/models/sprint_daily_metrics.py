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
    metric_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="指标快照业务标识"
    )
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
        Boolean, nullable=False, default=True, comment="本快照是否已采集禅道缺陷指标"
    )
    bug_details_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="采集的禅道缺陷详细快照 JSON"
    )
    bug_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷总数"
    )
    bug_resolved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷已解决数"
    )
    bug_closed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷已关闭数"
    )
    bug_unresolved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷未解决数"
    )
    bug_fatal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷致命数"
    )
    bug_serious: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷严重数"
    )
    bug_normal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷一般数"
    )
    bug_suggestion: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="禅道缺陷建议数"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

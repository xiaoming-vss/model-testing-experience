from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class PerfSuiteRun(Base):
    __tablename__ = "perf_suite_runs"
    __table_args__ = (
        Index("idx_perf_suite_run_latest", "suite_id", "created_at", "id"),
        Index("idx_perf_suite_run_project_latest", "project_id", "created_at", "id"),
        {"comment": "性能测试集单次运行及串行执行汇总"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    suite_run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="性能测试集运行业务标识"
    )
    suite_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("perf_suites.suite_id", name="fk_perf_suite_runs_suite_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="性能测试集业务标识",
    )
    project_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="项目业务标识"
    )
    sprint_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="运行关联的迭代业务标识；空值表示历史运行未关联"
    )
    sprint_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        comment="运行创建时冻结的迭代名称；空值表示历史运行未关联",
    )
    suite_name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="发起运行时冻结的测试集名称"
    )
    environment_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, default="", comment="性能环境业务标识"
    )
    environment_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="发起运行时冻结的环境名称"
    )
    monitoring_connection_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, default="", comment="监控接入业务标识"
    )
    monitoring_connection_name: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", comment="发起运行时冻结的监控接入名称"
    )
    monitoring_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="发起运行时冻结的监控接入公开快照 JSON，不含凭据"
    )
    trigger_user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="本次运行发起者用户业务标识"
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", comment="运行触发方式：manual"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="queued",
        comment="性能测试集运行状态：queued/running/stopping/completed/failed/stopped/canceled",
    )
    outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=("性能测试集运行结果分类：inconclusive/stopped/execution_error"),
    )
    total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行计划执行的用例数"
    )
    completed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已完成用例数"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行失败用例数"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="未执行或停止跳过的用例数"
    )
    error_message: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="执行或同步错误信息"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行开始时间（UTC）"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行结束时间（UTC）"
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行耗时，单位毫秒"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class PerfSuiteRunItem(Base):
    __tablename__ = "perf_suite_run_items"
    __table_args__ = (
        Index("idx_perf_suite_run_item_order", "suite_run_id", "order_no"),
        Index("idx_perf_suite_run_item_child_run", "child_run_id"),
        {"comment": "性能测试集运行中的有序用例执行条目及子运行关联"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    item_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="运行条目业务标识"
    )
    suite_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "perf_suite_runs.suite_run_id",
            name="fk_perf_suite_run_items_suite_run_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
        comment="性能测试集运行业务标识",
    )
    case_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="性能用例业务标识"
    )
    case_name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="发起运行时冻结的用例名称"
    )
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="串行执行顺序"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="pending",
        comment="性能测试集条目状态：pending/queued/running/completed/failed/stopped/canceled/skipped",
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="子运行结果")
    child_run_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="关联的单用例运行业务标识"
    )
    error_message: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="执行或同步错误信息"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行开始时间（UTC）"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行结束时间（UTC）"
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行耗时，单位毫秒"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

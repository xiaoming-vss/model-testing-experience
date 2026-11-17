from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class PerfRun(Base):
    __tablename__ = "perf_runs"
    __table_args__ = (
        Index("idx_perf_run_case_latest", "case_id", "created_at", "id"),
        Index("idx_perf_run_project_latest", "project_id", "created_at", "id"),
        Index("idx_perf_run_status_created", "status", "created_at"),
        {"comment": "性能测试运行、冻结规格、执行事实与阈值结果"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="运行业务标识"
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("perf_cases.case_id", name="fk_perf_runs_case", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="性能用例业务标识",
    )
    project_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="项目业务标识"
    )
    case_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="发起运行时冻结的用例版本号"
    )
    case_name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="发起运行时冻结的用例名称"
    )
    environment_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, default="", comment="性能环境业务标识"
    )
    environment_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", comment="发起运行时冻结的环境名称"
    )
    monitoring_connection_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        default="",
        comment="监控接入业务标识",
    )
    monitoring_connection_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="",
        comment="发起运行时冻结的监控接入名称",
    )
    trigger_user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="本次运行发起者用户业务标识"
    )
    trigger_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", comment="运行触发方式"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="queued",
        comment="queued/running/stopping/completed/failed/stopped/canceled",
    )
    outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="passed/threshold_failed/inconclusive/execution_error/stopped",
    )
    case_yaml: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"),
        nullable=False,
        default="",
        comment="发起运行时冻结的 YAML 用例正文",
    )
    spec_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="下发 Worker 的脱敏运行规格 JSON"
    )
    data_files_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="本次运行冻结的数据文件元数据 JSON"
    )
    private_payload: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"),
        nullable=True,
        comment="加密保存的完整运行规格、环境变量和 Remote Write 写凭据",
    )
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="k6 精简 summary JSON"
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Worker 回传的执行事实 JSON，不含 summary/logTail"
    )
    flags_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="运行结果标记 JSON"
    )
    log_tail: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="脱敏后的 k6 日志尾部"
    )
    error_message: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="执行或同步错误信息"
    )
    k6_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="实际使用的 k6 版本"
    )
    template_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="固定 k6 模板版本"
    )
    script_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="生成脚本的 SHA-256"
    )
    runner_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="执行 Worker 的主机与 CPU 信息 JSON"
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

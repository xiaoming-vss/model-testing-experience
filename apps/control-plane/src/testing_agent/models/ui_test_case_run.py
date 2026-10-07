from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class UiTestCaseRun(Base):
    __tablename__ = "ui_test_case_runs"
    __table_args__ = (
        Index("idx_ui_case_run_latest", "case_id", "created_at", "id"),
        {"comment": "UI 用例单次运行及步骤结果、执行追踪"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="运行业务标识"
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ui_test_cases.case_id", name="fk_ui_test_case_runs_case_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
        comment="测试用例业务标识",
    )
    suite_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="测试集或套件业务标识"
    )
    requirement_id = ""  # Response-only: derived from the current suite ownership.
    sprint_id = ""  # Response-only: derived from the current suite ownership.
    project_id = ""  # Response-only: derived from the current suite ownership.
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
        default="pending",
        comment="pending/queued/claimed/running/success/failed/error/canceled/skipped",
    )
    trace_path: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", comment="浏览器执行追踪文件路径"
    )
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="执行输入或业务内容快照 JSON"
    )
    step_results_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="逐步骤执行结果 JSON"
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

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiCaseRun(Base):
    __tablename__ = "api_case_runs"
    __table_args__ = (
        Index("idx_api_case_run_latest", "case_id", "created_at", "id"),
        {"comment": "API 用例单次运行及请求、响应、断言和提取结果"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="运行业务标识"
    )
    collection_run_id: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True, comment="API 集合运行业务标识"
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("api_cases.case_id", name="fk_api_case_runs_case"),
        index=True,
        nullable=False,
        comment="测试用例业务标识",
    )
    collection_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="API 集合业务标识"
    )
    requirement_id = ""  # Response-only; resolved through current collection ownership.
    sprint_id = ""  # Response-only; resolved through current collection ownership.
    project_id = ""  # Response-only; resolved through current collection ownership.
    environment_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="API 环境业务标识"
    )
    private_payload: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"),
        nullable=True,
        comment="使用集成密钥加密的个人执行材料，仅供本次运行使用",
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
        default="pending",
        comment="pending/queued/claimed/running/success/failed/error/canceled/skipped",
    )
    request_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="实际请求的脱敏快照 JSON"
    )
    response_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="响应内容的脱敏快照 JSON"
    )
    runtime_vars_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="运行期间变量及其值的 JSON"
    )
    extract_results_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="变量提取规则执行结果 JSON"
    )
    assert_results_json: Mapped[list[Any] | None] = mapped_column(
        JSON, nullable=True, comment="断言规则执行结果 JSON"
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

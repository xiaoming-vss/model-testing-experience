from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class ApiCollectionRun(Base):
    __tablename__ = "api_collection_runs"
    __table_args__ = {"comment": "API 集合单次运行及结果汇总"}
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    collection_run_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="API 集合运行业务标识"
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_collections.collection_id",
            name="fk_api_collection_runs_collection_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
        comment="API 集合业务标识",
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
    total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行用例总数"
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行用例成功数"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行用例失败数"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行用例异常数"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次运行用例跳过数"
    )
    runtime_vars_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="运行期间变量及其值的 JSON"
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


class ApiCollectionRunItem(Base):
    __tablename__ = "api_collection_run_items"
    __table_args__ = (
        Index("idx_collection_run_item_order", "collection_run_id", "order_no"),
        {"comment": "API 集合运行中的有序用例执行条目"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    item_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="运行条目业务标识"
    )
    collection_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_collection_runs.collection_run_id",
            name="fk_api_collection_run_items_collection_run_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
        comment="API 集合运行业务标识",
    )
    case_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "api_cases.case_id", name="fk_api_collection_run_items_case_id", ondelete="CASCADE"
        ),
        index=True,
        nullable=False,
        comment="测试用例业务标识",
    )
    case_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("api_case_runs.run_id", name="fk_api_collection_run_items_case_run"),
        index=True,
        nullable=True,
        comment="关联 API 用例运行业务标识",
    )
    order_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="执行或展示顺序"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
        default="pending",
        comment="pending/queued/claimed/running/success/failed/error/canceled/skipped",
    )
    continue_on_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="失败后是否继续执行后续用例"
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

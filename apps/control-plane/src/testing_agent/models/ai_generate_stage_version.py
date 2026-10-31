"""Approved, immutable stage versions shared by a requirement generation chain.

A row is created only when a stage draft is approved. Content is copied from the
source attempt so deleting an old run does not erase already approved versions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt

CONTENT = Text().with_variant(LONGTEXT(), "mysql")


class AiGenerateStageVersion(Base):
    __tablename__ = "ai_generate_stage_versions"
    __table_args__ = (
        UniqueConstraint("version_id", name="uq_ai_stage_version_id"),
        UniqueConstraint("task_id", "stage", "version_no", name="uq_ai_stage_version_number"),
        UniqueConstraint("task_id", "stage", "attempt_id", name="uq_ai_stage_version_attempt"),
        Index("idx_ai_stage_version_chain", "task_id", "stage", "version_no"),
        {"comment": "AI 生成链各阶段审核通过后形成的不可变版本及来源尝试快照"},
    )
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="数据库内部主键"
    )
    version_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="阶段版本业务标识")
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_tasks.task_id",
            name="fk_ai_stage_versions_task",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="阶段版本所属生成链任务业务标识",
    )
    stage: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="阶段版本对应的 AI 阶段标识"
    )
    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="同一生成链同一阶段内从 1 开始递增的版本号"
    )
    run_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="产生该版本的运行业务标识"
    )
    attempt_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="产生该版本的阶段尝试主键标识"
    )
    artifact_content: Mapped[str] = mapped_column(
        CONTENT, nullable=False, comment="审核通过时的阶段产物正文快照"
    )
    artifact_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="text", comment="产物格式：json/text"
    )
    artifact_context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="审核通过时的阶段产物上下文 JSON"
    )
    upstream_versions_json: Mapped[dict[str, str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="生成该版本时读取的上游阶段及版本业务标识映射 JSON",
    )
    based_on_old: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否基于非最新上游版本审核通过",
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="阶段审核人用户业务标识"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="阶段审核通过时间（UTC）"
    )
    review_comment: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="阶段审核意见"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")

"""Formal-asset import provenance for an approved generation-chain leaf version.

One row is written for each formal target changed by an import. The target's
``effective_import_id`` points at its most recent row. Version hard deletion
removes these rows while the formal target and its cases remain.
"""

from __future__ import annotations

from datetime import datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk


class AiGenerateVersionImport(Base):
    __tablename__ = "ai_generate_version_imports"
    __table_args__ = (
        UniqueConstraint("import_id", name="uq_ai_version_import_id"),
        Index("idx_ai_version_import_leaf", "task_id", "version_id"),
        Index("idx_ai_version_import_target", "target_type", "target_id", "imported_at"),
        {"comment": "已通过叶子版本导入正式资产的来源、父链和变更用例记录"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    import_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="导入记录业务标识")
    task_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_tasks.task_id",
            name="fk_ai_version_import_task",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="叶子版本所属生成链任务业务标识",
    )
    version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "ai_generate_stage_versions.version_id",
            name="fk_ai_version_import_version",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="被导入的叶子阶段版本业务标识",
    )
    leaf_stage: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="被导入叶子版本对应的阶段标识"
    )
    target_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="正式目标类型：function_suite/api_collection/ui_suite",
    )
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="正式目标业务标识")
    parent_versions_json: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True, comment="叶子版本的完整上游阶段与版本标识映射 JSON"
    )
    changed_case_ids_json: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="本次导入新增或覆盖的正式用例业务标识列表 JSON"
    )
    target_case_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="导入完成后正式目标内的用例总数",
    )
    mixed_source: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="正式目标是否仍有本次导入未覆盖的旧来源用例",
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="叶子版本审核人用户业务标识"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="叶子版本审核通过时间（UTC）"
    )
    review_comment: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="叶子版本审核意见"
    )
    imported_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="执行导入的用户业务标识"
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="正式资产导入时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")

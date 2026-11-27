"""Self-contained formal-import evidence, independent of legacy versions and attempts."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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


class AiGenerateImportRequest(Base):
    __tablename__ = "ai_generate_import_requests"
    __table_args__ = ({"comment": "正式用例导入操作的幂等身份及结果"},)

    request_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="导入幂等请求业务标识"
    )
    request_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="导入请求及预览前提的指纹"
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="导入目标需求审计标识；历史目标已缺失时为空字符串"
    )
    actor_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="执行导入的用户审计标识"
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="导入完成后的回执标识与结果摘要"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="导入操作完成时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="导入请求创建时间（UTC）")


class AiGenerateImport(Base):
    __tablename__ = "ai_generate_imports"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "target_type", "target_id", name="uq_ai_import_request_target"
        ),
        Index("idx_ai_import_target", "target_type", "target_id", "imported_at"),
        Index("idx_ai_import_requirement_stage", "requirement_id", "kind", "stage"),
        Index("idx_ai_import_candidate_snapshot", "source_candidate_id", "source_snapshot_id"),
        CheckConstraint(
            "source_kind IN ('current', 'standalone', 'legacy')", name="ck_ai_import_source_kind"
        ),
        CheckConstraint("target_case_count >= 0", name="ck_ai_import_target_count"),
        {"comment": "正式测试资产导入的自包含来源与变更回执"},
    )

    import_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="正式资产导入回执业务标识"
    )
    request_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_import_requests.request_id", ondelete="RESTRICT"),
        nullable=False,
        comment="本次导入的幂等请求业务标识",
    )
    source_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="来源类型：current/standalone/legacy（legacy 为历史证据）",
    )
    requirement_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="导入目标需求审计标识；历史目标已缺失时为空字符串"
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="来源生成任务审计标识")
    kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment=(
            "来源生成链或独立任务类型：requirement_analysis/function/api/ui 或 reposito"
            "ry_profile/test_report_generate/code_risk_analysis/test_orde"
            "r_graph/test_order_case_visualization"
        ),
    )
    stage: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment=(
            "被导入内容所属阶段：requirement_review/extracting_text/historical_requ"
            "irement_relations/historical_test_case_verification/requirem"
            "ent_analysis/case_names/detailed_cases/interface_extract/api"
            "_design/generate/ui_surface/ui_design/ui_yaml"
        ),
    )
    source_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="来源尝试审计标识，不作为存活依赖"
    )
    source_candidate_id: Mapped[str | None] = mapped_column(
        String(64), comment="来源候选审计标识，不作为存活依赖"
    )
    source_snapshot_id: Mapped[str | None] = mapped_column(
        String(64), comment="来源候选快照审计标识"
    )
    source_content_token: Mapped[str | None] = mapped_column(
        String(64), comment="导入时当前内容并发令牌"
    )
    content: Mapped[str] = mapped_column(
        CONTENT, nullable=False, comment="实际导入的生成产物正文快照"
    )
    format: Mapped[str] = mapped_column(
        String(20), nullable=False, comment=("实际导入产物正文格式：json/text/yaml")
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128), comment="导入产物正文指纹；未知时为空"
    )
    basis_hash: Mapped[str | None] = mapped_column(
        String(128), comment="来源实际输入依据指纹；未知时为空"
    )
    lineage_hash: Mapped[str | None] = mapped_column(
        String(128), comment="导入时完整来源闭包指纹；未知时为空"
    )
    source_manifest_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="导入时冻结的来源清单；未知时为空"
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="导入时上游产物及脱敏输入摘要快照"
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(64), comment="采用或审核操作者审计标识"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="采用或审核时间（UTC）"
    )
    review_comment: Mapped[str | None] = mapped_column(Text, comment="采用或审核意见")
    target_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="正式目标类型：function_suite/api_collection/ui_suite"
    )
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="正式目标审计标识")
    changed_case_ids_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, comment="本次导入变更的正式用例标识列表"
    )
    target_case_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="导入后正式目标的用例总数"
    )
    mixed_source: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="正式目标是否仍有本次未覆盖的用例：true/false"
    )
    imported_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="执行导入的用户审计标识"
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="正式资产导入时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="导入回执创建时间（UTC）")

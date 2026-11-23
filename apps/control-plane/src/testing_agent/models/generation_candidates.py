"""Storage for requirement-chain candidates and their single adopted content.

These tables do not switch the existing generation workflow by themselves.
Attempt identifiers are audit references, not foreign keys: retained content must
survive cleanup of individual attempts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt

CONTENT = Text().with_variant(LONGTEXT(), "mysql")


class RequirementGenerationChain(Base):
    __tablename__ = "requirement_generation_chains"
    __table_args__ = (
        UniqueConstraint("requirement_id", "kind", name="uq_req_generation_chain_kind"),
        UniqueConstraint("task_id", name="uq_req_generation_chain_task"),
        {"comment": "需求各类生成流程的唯一当前任务容器"},
    )

    chain_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="需求生成链业务标识"
    )
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("requirements.requirement_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属需求业务标识",
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, comment="需求生成链类型")
    task_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generate_tasks.task_id", ondelete="RESTRICT"),
        nullable=False,
        comment="当前链绑定的生成任务业务标识",
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="生成链创建时间（UTC）")


class AiGenerationCandidate(Base):
    __tablename__ = "ai_generation_candidates"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_ai_candidate_snapshot"),
        UniqueConstraint("stage_id", "origin_attempt_id", name="uq_ai_candidate_stage_origin"),
        Index("idx_ai_candidate_chain_stage", "chain_id", "stage_id", "created_at"),
        {"comment": "需求生成链阶段候选内容及冻结来源"},
    )

    candidate_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="阶段候选业务标识"
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="候选正文及来源快照固定标识"
    )
    chain_id: Mapped[str] = mapped_column(
        ForeignKey("requirement_generation_chains.chain_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属需求生成链业务标识",
    )
    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generation_stages.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属稳定阶段业务标识",
    )
    origin_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="产生候选的尝试审计标识"
    )
    current_attempt_id: Mapped[str | None] = mapped_column(
        String(64), comment="最近编辑候选的尝试审计标识"
    )
    derived_from_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_generation_candidates.candidate_id", ondelete="RESTRICT"),
        comment="派生候选的原候选业务标识",
    )
    content: Mapped[str] = mapped_column(CONTENT, nullable=False, comment="候选产物正文快照")
    format: Mapped[str] = mapped_column(String(20), nullable=False, comment="候选产物正文格式")
    context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="候选产物上下文"
    )
    candidate_token: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="候选并发修改令牌"
    )
    disposition: Mapped[str] = mapped_column(String(20), nullable=False, comment="候选处置状态")
    generation_mode: Mapped[str] = mapped_column(String(20), nullable=False, comment="候选生成模式")
    source_manifest_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="候选冻结来源清单"
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="候选实际输入及来源快照"
    )
    lineage_hash: Mapped[str | None] = mapped_column(String(128), comment="完整来源闭包指纹")
    content_hash: Mapped[str | None] = mapped_column(String(128), comment="候选正文内容指纹")
    basis_hash: Mapped[str | None] = mapped_column(String(128), comment="候选实际输入依据指纹")
    frozen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="候选因采用或被引用而冻结的时间（UTC）"
    )
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="创建候选的用户业务标识；空字符串表示历史来源未知"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="候选创建时间（UTC）")


class AiGenerationStageContent(Base):
    __tablename__ = "ai_generation_stage_contents"
    __table_args__ = (
        UniqueConstraint("chain_id", "stage", name="uq_ai_stage_content_chain_stage"),
        {"comment": "需求生成链阶段唯一采用内容及空槽令牌"},
    )

    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generation_stages.id", ondelete="CASCADE"),
        primary_key=True,
        comment="当前内容所属稳定阶段业务标识",
    )
    chain_id: Mapped[str] = mapped_column(
        ForeignKey("requirement_generation_chains.chain_id", ondelete="CASCADE"),
        nullable=False,
        comment="当前内容所属需求生成链业务标识",
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, comment="当前内容所属阶段类型")
    content: Mapped[str | None] = mapped_column(CONTENT, comment="当前确认正文；空槽时为空")
    format: Mapped[str | None] = mapped_column(String(20), comment="当前确认正文格式")
    context_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="当前确认正文上下文"
    )
    content_hash: Mapped[str | None] = mapped_column(String(128), comment="当前确认正文内容指纹")
    basis_hash: Mapped[str | None] = mapped_column(
        String(128), comment="当前确认内容的输入依据指纹"
    )
    content_token: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="当前内容或空槽并发修改令牌"
    )
    source_manifest_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="当前确认内容冻结来源清单"
    )
    source_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON(none_as_null=True), comment="当前确认内容的实际输入及来源快照"
    )
    lineage_hash: Mapped[str | None] = mapped_column(
        String(128), comment="确认时核验的完整来源闭包指纹"
    )
    source_attempt_id: Mapped[str | None] = mapped_column(String(64), comment="来源尝试审计标识")
    source_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_generation_candidates.candidate_id", ondelete="RESTRICT"),
        comment="当前采用的候选业务标识；空槽时为空",
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(64), comment="确认当前内容的用户业务标识"
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="当前内容确认时间（UTC）"
    )
    comment: Mapped[str | None] = mapped_column(Text, comment="当前内容确认意见")
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="当前内容标记待更新时间（UTC）"
    )
    invalidated_reason: Mapped[str | None] = mapped_column(
        String(512), comment="当前内容标记待更新原因"
    )


class AiGenerationReviewReceipt(Base):
    __tablename__ = "ai_generation_review_receipts"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_ai_generation_review_request"),
        {"comment": "阶段候选审核操作的幂等回执与审计信息"},
    )

    receipt_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="阶段审核回执业务标识"
    )
    request_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="审核操作幂等请求标识"
    )
    request_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="审核请求内容指纹"
    )
    stage_id: Mapped[str] = mapped_column(
        ForeignKey("ai_generation_stages.id", ondelete="CASCADE"),
        nullable=False,
        comment="审核所属稳定阶段标识",
    )
    candidate_id: Mapped[str | None] = mapped_column(String(64), comment="审核目标候选审计标识")
    attempt_id: Mapped[str | None] = mapped_column(String(64), comment="审核来源尝试审计标识")
    decision: Mapped[str] = mapped_column(String(20), nullable=False, comment="本次审核操作结论")
    result_content_token: Mapped[str | None] = mapped_column(
        String(64), comment="审核完成时当前内容令牌"
    )
    result_candidate_token: Mapped[str | None] = mapped_column(
        String(64), comment="候选操作完成时的结果候选令牌"
    )
    result_candidate_id: Mapped[str | None] = mapped_column(
        String(64), comment="候选派生操作生成的候选标识"
    )
    result_snapshot_id: Mapped[str | None] = mapped_column(
        String(64), comment="候选派生操作生成的快照标识"
    )
    comment: Mapped[str | None] = mapped_column(Text, comment="审核或候选处置意见")
    actor_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="审核操作者用户业务标识；空字符串表示历史审核人未知"
    )
    continuation_request_id: Mapped[str | None] = mapped_column(
        String(64), comment="审核后继续生成的请求标识"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="审核回执创建时间（UTC）")

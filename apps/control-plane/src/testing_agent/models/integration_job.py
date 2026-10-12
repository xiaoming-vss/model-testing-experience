"""Integration execution history survives deletion of its referenced business resources."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class IntegrationJob(Base):
    __tablename__ = "integration_jobs"
    __table_args__ = (
        UniqueConstraint("actor_user_id", "request_id", name="uk_integration_job_request"),
        UniqueConstraint("active_scope", name="uk_integration_job_active_scope"),
        UniqueConstraint("active_target", name="uk_integration_job_active_target"),
        UniqueConstraint("claim_key", name="uk_integration_job_claim_key"),
        Index("ix_integration_jobs_queue", "status", "created_at", "id"),
        Index("ix_integration_jobs_lease", "status", "lease_expires_at"),
        Index("ix_integration_jobs_bug", "project_id", "bug_id", "id"),
        Index("ix_integration_jobs_retention", "status", "archived_at", "finished_at", "id"),
        Index("ix_integration_jobs_project_created", "project_id", "created_at"),
        {"comment": "独立集成任务队列及冻结输入、目标执行权、租约和恢复状态"},
    )

    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    job_id: Mapped[str] = mapped_column(String(64), unique=True, comment="集成任务业务标识")
    protocol_version: Mapped[int] = mapped_column(Integer, comment="集成执行协议版本")
    task_type: Mapped[str] = mapped_column(String(40), comment="任务类型")
    project_id: Mapped[str] = mapped_column(String(64), comment="项目业务标识")
    bug_id: Mapped[str] = mapped_column(String(64), comment="平台 Bug 业务标识")
    actor_user_id: Mapped[str] = mapped_column(
        String(64), comment="本次操作人用户业务标识；外部调用使用其本人授权"
    )
    service_id: Mapped[str] = mapped_column(String(64), comment="项目共享服务业务标识")
    connection_id: Mapped[str] = mapped_column(String(64), comment="个人授权连接业务标识")
    target_key: Mapped[str] = mapped_column(
        String(64), comment="远端禅道实例地址的摘要键，用于目标执行权协调"
    )
    runtime_generation: Mapped[str] = mapped_column(
        String(64), comment="集成运行代次，用于拒绝恢复前或旧环境 Worker 请求"
    )
    request_id: Mapped[str] = mapped_column(String(64), comment="客户端请求幂等标识")
    request_digest: Mapped[str] = mapped_column(String(64), comment="幂等请求内容摘要")
    input_revision: Mapped[str] = mapped_column(String(64), comment="冻结输入版本摘要")
    target_revision: Mapped[str] = mapped_column(String(64), comment="冻结目标及授权版本摘要")
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="冻结的领域输入、个人授权版本和目标快照 JSON"
    )
    mapping_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="已确认步骤产生的远端映射 JSON"
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="执行结果及核对证据 JSON"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="queued",
        comment="集成任务状态：queued/claimed/running/succeeded/partial/failed/unknown/canceled/quarantined",
    )
    active_scope: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="当前活跃 Bug 执行范围唯一键；空值表示已释放"
    )
    active_target: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="当前活跃远端目标唯一键；空值表示已释放"
    )
    worker_id: Mapped[str] = mapped_column(
        String(128), default="", comment="领取或执行任务的 Worker 标识"
    )
    claim_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Worker 领取幂等键"
    )
    claim_generation: Mapped[int] = mapped_column(
        Integer, default=0, comment="任务领取代次，拒绝旧领取请求"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="当前执行租约到期时间（UTC）"
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="当前领取的最近心跳时间（UTC）"
    )
    first_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务首次被领取时间（UTC）"
    )
    queue_wait_ms: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="首次领取前的排队耗时，单位毫秒"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行结束时间（UTC）"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="任务取消时间（UTC）"
    )
    recovery_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否必须核对未决写入或恢复后的外部状态"
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="历史输入和快照清理归档时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class IntegrationJobStep(Base):
    __tablename__ = "integration_job_steps"
    __table_args__ = (
        UniqueConstraint("job_id", "step_key", name="uk_integration_job_step"),
        Index("ix_integration_job_steps_intent", "status", "updated_at"),
        Index("ix_integration_job_steps_updated", "updated_at"),
        Index("ix_integration_job_steps_remote_recorded", "remote_recorded_at"),
        {"comment": "集成步骤及持久化远端写入意图、幂等回执和执行证据"},
    )

    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integration_jobs.job_id", ondelete="CASCADE"),
        comment="集成任务业务标识",
    )
    step_key: Mapped[str] = mapped_column(String(128), comment="任务内唯一的步骤键")
    kind: Mapped[str] = mapped_column(
        String(40),
        comment="远端步骤类型：create_bug/upload_attachment/update_description/update_fields",
    )
    dependencies_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, comment="本步骤依赖的前置步骤键列表 JSON"
    )
    input_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="冻结的步骤执行输入 JSON"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="pending/write_intent/succeeded/noop/failed/blocked/unknown/canceled",
    )
    operation_id: Mapped[str] = mapped_column(
        String(64), default="", comment="远端写入操作标识，用于结果核对与避免重复写入"
    )
    prepare_request_id: Mapped[str] = mapped_column(
        String(64), default="", comment="写入准备请求幂等标识"
    )
    intent_worker_id: Mapped[str] = mapped_column(
        String(128), default="", comment="获准写入意图对应的 Worker 标识"
    )
    intent_generation: Mapped[int] = mapped_column(
        Integer, default=0, comment="写入意图对应的领取代次"
    )
    permit_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="本次远端写许可的到期时间（UTC）"
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="执行结果及核对证据 JSON"
    )
    receipts_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, comment="历次远端操作结果的幂等回执列表 JSON"
    )
    remote_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="远端操作耗时观测，单位毫秒，不参与领域结果比较"
    )
    remote_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次记录远端操作结果时间（UTC）"
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次失败时间（UTC）"
    )
    unknown_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次进入未知写入结果时间（UTC）"
    )
    lease_lost_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次失去执行租约时间（UTC）"
    )
    access_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="首次发现执行授权撤销时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class IntegrationClaimReceipt(Base):
    """Persist empty claims and all generations, including response-loss retries."""

    __tablename__ = "integration_claim_receipts"
    __table_args__ = {"comment": "集成 Worker 领取请求回执；保留空领取及历次领取响应"}
    claim_key: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Worker 领取幂等键"
    )
    request_id: Mapped[str] = mapped_column(String(64), comment="客户端请求幂等标识")
    request_digest: Mapped[str] = mapped_column(String(64), comment="幂等请求内容摘要")
    job_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("integration_jobs.job_id"),
        nullable=True,
        index=True,
        comment="领取到的集成任务业务标识；空值表示未领取到任务",
    )
    response_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="领取请求原始响应 JSON；包括空领取响应"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")


class IntegrationRuntime(Base):
    """Durable restore fence, independent of deployment configuration switches."""

    __tablename__ = "integration_runtime"
    __table_args__ = {"comment": "数据库恢复后的持久化集成执行门控及运行代次"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="集成运行门控单例主键")
    restore_id: Mapped[str] = mapped_column(String(64), comment="数据库恢复批次标识")
    runtime_generation: Mapped[str] = mapped_column(
        String(64), comment="集成运行代次，用于拒绝恢复前或旧环境 Worker 请求"
    )
    worker_key_digest: Mapped[str] = mapped_column(
        String(64), comment="集成 Worker 专属认证密钥摘要"
    )
    blocked: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否阻止集成执行；部署开关不能绕过此门控"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")


class IntegrationWorkerPresence(Base):
    """Recent authenticated contact and capabilities; never an execution permit."""

    __tablename__ = "integration_worker_presence"
    __table_args__ = (
        Index("ix_integration_worker_presence_runtime", "runtime_generation", "last_seen_at"),
        Index("ix_integration_worker_presence_seen", "last_seen_at"),
        {"comment": "集成 Worker 最近联系及能力声明；此记录不授予执行权限"},
    )
    worker_id: Mapped[str] = mapped_column(
        String(128), primary_key=True, comment="领取或执行任务的 Worker 标识"
    )
    runtime_generation: Mapped[str] = mapped_column(
        String(64), comment="集成运行代次，用于拒绝恢复前或旧环境 Worker 请求"
    )
    protocol_versions: Mapped[list[int]] = mapped_column(
        JSON, comment="Worker 支持的协议版本列表 JSON"
    )
    task_types: Mapped[list[str]] = mapped_column(
        JSON, comment="Worker 支持的集成任务类型列表 JSON"
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="Worker 最近成功联系时间（UTC）"
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Worker 最近心跳联系时间（UTC）"
    )


class IntegrationRestoreReview(Base):
    """Readonly facts or retained isolation, scoped to one restored database generation."""

    __tablename__ = "integration_restore_reviews"
    __table_args__ = (
        UniqueConstraint(
            "restore_id", "scope_type", "scope_id", name="uk_integration_restore_scope"
        ),
        Index("ix_integration_restore_project", "restore_id", "project_id", "decision"),
        {"comment": "数据库恢复后按范围保存的外部只读核对事实与隔离决定"},
    )
    id: Mapped[IdPk] = mapped_column(comment="数据库内部主键")
    review_id: Mapped[str] = mapped_column(String(64), unique=True, comment="恢复核对记录业务标识")
    restore_id: Mapped[str] = mapped_column(String(64), comment="数据库恢复批次标识")
    scope_type: Mapped[str] = mapped_column(String(10), comment="恢复核对范围类型：bug/job")
    scope_id: Mapped[str] = mapped_column(String(64), comment="恢复核对范围业务标识")
    project_id: Mapped[str] = mapped_column(String(64), comment="项目业务标识")
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="本次操作人用户业务标识；外部调用使用其本人授权"
    )
    decision: Mapped[str] = mapped_column(String(20), comment="核对决定：verified/isolated")
    state_digest: Mapped[str] = mapped_column(
        String(64), comment="核对时本地关联、目标及授权状态摘要"
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="审核或核对时间（UTC）"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="记录创建时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="记录最后更新时间（UTC）")

"""Stable remote case identities and append-only write attempts, retained after asset deletion."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from testing_agent.db.base import Base, CreatedAt, IdPk, UpdatedAt


class FunctionCaseRemoteIdentity(Base):
    __tablename__ = "function_case_remote_identities"
    __table_args__ = (
        UniqueConstraint("instance_key", "case_id", name="uk_function_remote_local"),
        UniqueConstraint("instance_key", "remote_case_id", name="uk_function_remote_identity"),
        Index("ix_function_remote_project", "project_id", "id"),
        {"comment": "功能用例与禅道实例内用例的稳定映射；删除本地资产后保留写入证据"},
    )
    id: Mapped[IdPk] = mapped_column(comment="映射记录的数据库内部主键")
    project_id: Mapped[str] = mapped_column(
        String(64), comment="平台项目业务标识；用于当前权限检查"
    )
    case_id: Mapped[str] = mapped_column(
        String(64), comment="平台功能用例固定业务编号；不按标题匹配"
    )
    instance_key: Mapped[str] = mapped_column(String(64), comment="规范化禅道实例地址的哈希")
    remote_case_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="禅道用例编号；空值表示尚未确认创建或绑定"
    )
    target_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="确认映射时的产品、项目、执行与需求编号；不包含凭据"
    )
    revision: Mapped[int] = mapped_column(
        Integer, default=0, comment="映射版本；核对和写入结果更新时递增"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="映射预留时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="映射最近确认时间（UTC）")


class FunctionCasePushOperation(Base):
    __tablename__ = "function_case_push_operations"
    __table_args__ = (
        UniqueConstraint("actor_user_id", "request_id", "case_id", name="uk_function_push_request"),
        UniqueConstraint("active_key", name="uk_function_push_active"),
        Index("ix_function_push_project", "project_id", "id"),
        Index("ix_function_push_identity", "identity_id", "id"),
        {"comment": "功能用例远端写入意图及回执；未知结果阻止重新写入，历史证据不可级联删除"},
    )
    id: Mapped[IdPk] = mapped_column(comment="操作记录的数据库内部主键")
    operation_id: Mapped[str] = mapped_column(
        String(64), unique=True, comment="一次远端写入的不可变操作编号"
    )
    identity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "function_case_remote_identities.id",
            ondelete="RESTRICT",
            name="fk_function_push_identity",
        ),
        comment="稳定映射记录内部主键；历史操作引用不允许被删除",
    )
    project_id: Mapped[str] = mapped_column(String(64), comment="操作所属平台项目业务标识")
    case_id: Mapped[str] = mapped_column(String(64), comment="本次操作的原平台用例编号")
    actor_user_id: Mapped[str] = mapped_column(
        String(64), comment="发起写入的用户编号；凭据不进入账本"
    )
    request_id: Mapped[str] = mapped_column(String(64), comment="客户端提交编号；重试复用相同编号")
    request_digest: Mapped[str] = mapped_column(
        String(64), comment="原提交目标、选择与内容的摘要；同编号不同内容拒绝"
    )
    active_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="未决映射的互斥键；明确完成后置空，未知结果继续占用"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        comment="prepared/succeeded/failed/unknown；prepared 已获一次写许可，重试不再授予",
    )
    action: Mapped[str] = mapped_column(
        String(20), comment="create/update；历史同名需显式选择绑定或新建"
    )
    target_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="写入前冻结的远端目标和已绑定编号"
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="写入前冻结的用例内容，不含授权材料"
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, comment="安全结果回执及人工核对证据，不存原始远端响应"
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="一次写许可截止时间（UTC）；到期只允许核对，不自动重试"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="远端调用前意图持久化时间（UTC）")
    updated_at: Mapped[UpdatedAt] = mapped_column(comment="最近回执或核对更新时间（UTC）")


class FunctionCasePushRequest(Base):
    __tablename__ = "function_case_push_requests"
    __table_args__ = (
        UniqueConstraint("actor_user_id", "request_id", name="uk_function_push_batch"),
        {"comment": "功能用例推送批次原始选择及内容摘要；重试不自动纳入新增用例"},
    )
    id: Mapped[IdPk] = mapped_column(comment="批次记录内部主键")
    actor_user_id: Mapped[str] = mapped_column(String(64), comment="原批次发起用户业务标识")
    request_id: Mapped[str] = mapped_column(String(64), comment="客户端批次编号；同一用户全局唯一")
    project_id: Mapped[str] = mapped_column(String(64), comment="原批次所属项目业务标识")
    request_digest: Mapped[str] = mapped_column(
        String(64), comment="原客户端参数和资源范围摘要；重试变更参数拒绝"
    )
    target_digest: Mapped[str] = mapped_column(
        String(64), comment="原远端实例与目标摘要；绑定变化后不得重用批次"
    )
    manifest_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="按用例编号冻结所属测试集和原内容摘要；不包含正文或凭据"
    )
    created_at: Mapped[CreatedAt] = mapped_column(comment="批次首次提交时间（UTC）")

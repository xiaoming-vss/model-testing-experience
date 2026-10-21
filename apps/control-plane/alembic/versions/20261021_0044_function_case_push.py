"""Persist stable Zentao testcase identities and write evidence."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0044"
down_revision = "20261020_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "function_case_remote_identities",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
            primary_key=True,
            autoincrement=True,
            comment="映射记录的数据库内部主键",
        ),
        sa.Column(
            "project_id",
            sa.String(64),
            nullable=False,
            comment="平台项目业务标识；用于当前权限检查",
        ),
        sa.Column(
            "case_id",
            sa.String(64),
            nullable=False,
            comment="平台功能用例固定业务编号；不按标题匹配",
        ),
        sa.Column(
            "instance_key", sa.String(64), nullable=False, comment="规范化禅道实例地址的哈希"
        ),
        sa.Column(
            "remote_case_id",
            sa.Integer(),
            nullable=True,
            comment="禅道用例编号；空值表示尚未确认创建或绑定",
        ),
        sa.Column(
            "target_json",
            sa.JSON(),
            nullable=False,
            comment="确认映射时的产品、项目、执行与需求编号；不包含凭据",
        ),
        sa.Column(
            "revision", sa.Integer(), nullable=False, comment="映射版本；核对和写入结果更新时递增"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, comment="映射预留时间（UTC）"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="映射最近确认时间（UTC）",
        ),
        sa.UniqueConstraint("instance_key", "remote_case_id", name="uk_function_remote_identity"),
        sa.UniqueConstraint("instance_key", "case_id", name="uk_function_remote_local"),
        comment="功能用例与禅道实例内用例的稳定映射；删除本地资产后保留写入证据",
    )
    op.create_index(
        "ix_function_remote_project", "function_case_remote_identities", ["project_id", "id"]
    )
    op.create_table(
        "function_case_push_operations",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
            primary_key=True,
            autoincrement=True,
            comment="操作记录的数据库内部主键",
        ),
        sa.Column(
            "operation_id", sa.String(64), nullable=False, comment="一次远端写入的不可变操作编号"
        ),
        sa.Column(
            "identity_id",
            sa.Integer(),
            nullable=False,
            comment="稳定映射记录内部主键；历史操作引用不允许被删除",
        ),
        sa.Column("project_id", sa.String(64), nullable=False, comment="操作所属平台项目业务标识"),
        sa.Column("case_id", sa.String(64), nullable=False, comment="本次操作的原平台用例编号"),
        sa.Column(
            "actor_user_id",
            sa.String(64),
            nullable=False,
            comment="发起写入的用户编号；凭据不进入账本",
        ),
        sa.Column(
            "request_id", sa.String(64), nullable=False, comment="客户端提交编号；重试复用相同编号"
        ),
        sa.Column(
            "request_digest",
            sa.String(64),
            nullable=False,
            comment="原提交目标、选择与内容的摘要；同编号不同内容拒绝",
        ),
        sa.Column(
            "active_key",
            sa.String(64),
            nullable=True,
            comment="未决映射的互斥键；明确完成后置空，未知结果继续占用",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="prepared/succeeded/failed/unknown；prepared 已获一次写许可，重试不再授予",
        ),
        sa.Column(
            "action",
            sa.String(20),
            nullable=False,
            comment="create/update；历史同名需显式选择绑定或新建",
        ),
        sa.Column(
            "target_json", sa.JSON(), nullable=False, comment="写入前冻结的远端目标和已绑定编号"
        ),
        sa.Column(
            "payload_json", sa.JSON(), nullable=False, comment="写入前冻结的用例内容，不含授权材料"
        ),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=False,
            comment="安全结果回执及人工核对证据，不存原始远端响应",
        ),
        sa.Column(
            "deadline",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="一次写许可截止时间（UTC）；到期只允许核对，不自动重试",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="远端调用前意图持久化时间（UTC）",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="最近回执或核对更新时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["function_case_remote_identities.id"],
            name="fk_function_push_identity",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("active_key", name="uk_function_push_active"),
        sa.UniqueConstraint(
            "actor_user_id", "request_id", "case_id", name="uk_function_push_request"
        ),
        sa.UniqueConstraint("operation_id", name="uq_function_case_push_operations_operation_id"),
        comment="功能用例远端写入意图及回执；未知结果阻止重新写入，历史证据不可级联删除",
    )
    op.create_index(
        "ix_function_push_identity", "function_case_push_operations", ["identity_id", "id"]
    )
    op.create_index(
        "ix_function_push_project", "function_case_push_operations", ["project_id", "id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("function_case_push_operations", "function_case_remote_identities"):
        if connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")):
            raise RuntimeError("Preserve testcase identity and write evidence; downgrade refused")
    op.drop_table("function_case_push_operations")
    op.drop_table("function_case_remote_identities")

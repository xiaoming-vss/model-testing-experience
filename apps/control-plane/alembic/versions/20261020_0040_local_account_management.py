"""Add local account lifecycle, super administrator and login throttling fields."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0040"
down_revision = "20261010_0039"
branch_labels = None
depends_on = None


USER_COLUMNS = (
    sa.Column(
        "is_super_admin",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("0"),
        comment="是否为系统预置的唯一超级管理员",
    ),
    sa.Column(
        "super_admin_slot",
        sa.Integer(),
        nullable=True,
        comment="超级管理员唯一占位；普通用户为空",
    ),
    sa.Column(
        "status",
        sa.String(20),
        nullable=False,
        server_default="active",
        comment="账号状态：active/disabled",
    ),
    sa.Column(
        "disabled_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="账号被禁用的时间（UTC）",
    ),
    sa.Column(
        "disabled_reason",
        sa.String(512),
        nullable=False,
        server_default="",
        comment="最近一次禁用原因",
    ),
    sa.Column(
        "disabled_by",
        sa.String(64),
        nullable=False,
        server_default="",
        comment="最近一次禁用操作人的用户业务标识",
    ),
    sa.Column(
        "must_change_password",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("0"),
        comment="是否要求下次登录前修改密码",
    ),
    sa.Column(
        "password_updated_at",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="最近一次密码修改或重置时间（UTC）",
    ),
    sa.Column(
        "token_version",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
        comment="令牌版本；递增后旧令牌全部失效",
    ),
    sa.Column(
        "failed_login_count",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
        comment="连续登录失败次数",
    ),
    sa.Column(
        "locked_until",
        sa.DateTime(timezone=True),
        nullable=True,
        comment="登录失败锁定截止时间（UTC）",
    ),
)


def upgrade() -> None:
    for column in USER_COLUMNS:
        op.add_column("users", column)
    with op.batch_alter_table("users") as batch:
        batch.create_unique_constraint("uq_users_super_admin_slot", ["super_admin_slot"])
    op.create_index("ix_users_status", "users", ["status"])
    # Any pre-existing platform administrator must change the initial password.
    op.execute(
        "UPDATE users SET super_admin_slot = 1, must_change_password = 1 WHERE is_super_admin = 1"
    )
    op.create_table(
        "login_rate_limits",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="数据库内部主键"
        ),
        sa.Column("username", sa.String(50), nullable=False, comment="登录用户名"),
        sa.Column("client_ip", sa.String(64), nullable=False, comment="客户端 IP 地址"),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="当前时间窗口内的失败尝试次数",
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="当前计数窗口开始时间（UTC）",
        ),
        sa.Column(
            "blocked_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="限流封禁截止时间（UTC）",
        ),
        sa.UniqueConstraint("username", "client_ip", name="uk_login_rate_limit_username_ip"),
        comment="按用户名和客户端地址限制登录尝试频率",
    )


def downgrade() -> None:
    op.drop_table("login_rate_limits")
    op.drop_index("ix_users_status", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_super_admin_slot", type_="unique")
        for column in reversed(USER_COLUMNS):
            batch.drop_column(column.name)

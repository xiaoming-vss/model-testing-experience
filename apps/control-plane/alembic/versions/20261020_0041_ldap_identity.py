"""Add stable LDAP identities without modifying existing local account state."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0041"
down_revision = "20261020_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    email = next(c for c in sa.inspect(op.get_bind()).get_columns("users") if c["name"] == "email")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email",
            existing_type=email["type"],
            existing_nullable=email["nullable"],
            existing_server_default=email.get("default"),
            comment="用户邮箱；新注册必填，存量账号可待补填",
        )
        batch.add_column(
            sa.Column(
                "auth_source",
                sa.String(16),
                nullable=False,
                server_default="local",
                comment="认证来源：local/ldap；关联后不自动恢复本地身份",
            )
        )
        batch.add_column(
            sa.Column(
                "external_id",
                sa.String(36),
                nullable=True,
                comment="LDAP 稳定身份 entryUUID；本地账号为空",
            )
        )
        batch.create_unique_constraint("uq_users_external_identity", ["auth_source", "external_id"])
        batch.alter_column(
            "status",
            existing_type=sa.String(20),
            existing_nullable=False,
            comment="账号状态：active/disabled/pending_ldap",
        )

    with op.batch_alter_table("login_rate_limits") as batch:
        batch.add_column(
            sa.Column(
                "auth_method",
                sa.String(16),
                nullable=False,
                server_default="local",
                comment="登录入口：local/ldap；隔离同名账号的失败限流",
            )
        )
        batch.drop_constraint("uk_login_rate_limit_username_ip", type_="unique")
        batch.create_unique_constraint(
            "uk_login_rate_limit_method_name_ip",
            ["auth_method", "username", "client_ip"],
        )


def downgrade() -> None:
    # Never silently discard external identities or convert pending users to active.
    connection = op.get_bind()
    count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM users WHERE auth_source <> 'local' OR status = 'pending_ldap'"
        )
    )
    if count:
        raise RuntimeError("Cannot remove LDAP schema while LDAP or pending accounts exist")
    # LDAP-only throttles have no meaning once the external auth schema is removed.
    op.execute("DELETE FROM login_rate_limits WHERE auth_method <> 'local'")
    with op.batch_alter_table("login_rate_limits") as batch:
        batch.drop_constraint("uk_login_rate_limit_method_name_ip", type_="unique")
        batch.drop_column("auth_method")
        batch.create_unique_constraint("uk_login_rate_limit_username_ip", ["username", "client_ip"])
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_external_identity", type_="unique")
        batch.drop_column("external_id")
        batch.drop_column("auth_source")
        batch.alter_column(
            "status",
            existing_type=sa.String(20),
            existing_nullable=False,
            comment="账号状态：active/disabled",
        )

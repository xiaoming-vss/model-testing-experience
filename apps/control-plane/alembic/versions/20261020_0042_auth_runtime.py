"""Persist authentication cutover completion and reconciliation coordination."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0042"
down_revision = "20261020_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "auth_runtime",
        sa.Column("id", sa.Integer(), primary_key=True, comment="单例主键，固定为 1"),
        sa.Column(
            "mode", sa.String(16), nullable=False, comment="已完成切换的认证模式：local/ldap"
        ),
        sa.Column(
            "fingerprint", sa.String(64), nullable=False, comment="当前 LDAP 配置摘要；本地模式为空"
        ),
        sa.Column(
            "generation",
            sa.Integer(),
            nullable=False,
            comment="认证配置切换代次，防止旧操作跨配置提交",
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最后一次模式切换时间（UTC）",
        ),
        sa.Column(
            "reconcile_owner",
            sa.String(64),
            nullable=False,
            comment="当前对账租约持有者；空值表示无人持有",
        ),
        sa.Column(
            "reconcile_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="对账租约截止时间（UTC）",
        ),
        comment="认证模式切换完成标记与 LDAP 对账协调",
    )
    op.bulk_insert(
        table,
        [{"id": 1, "mode": "local", "fingerprint": "", "generation": 0, "reconcile_owner": ""}],
    )


def downgrade() -> None:
    mode = op.get_bind().scalar(sa.text("SELECT mode FROM auth_runtime WHERE id = 1"))
    if mode != "local":
        raise RuntimeError("Switch authentication to local before removing runtime state")
    op.drop_table("auth_runtime")

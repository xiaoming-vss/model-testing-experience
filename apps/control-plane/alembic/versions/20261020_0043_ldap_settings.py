"""Persist LDAP settings managed through the administrator page."""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0043"
down_revision = "20261020_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_runtime",
        sa.Column(
            "ldap_config",
            sa.JSON(),
            nullable=True,
            comment="页面管理的 LDAP 配置；密码加密保存；空值表示尚未配置",
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT ldap_config FROM auth_runtime WHERE id=1")) is not None:
        raise RuntimeError("Export and clear page-managed LDAP configuration before downgrade")
    op.drop_column("auth_runtime", "ldap_config")

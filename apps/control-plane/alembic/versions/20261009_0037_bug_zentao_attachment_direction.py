"""Mark attachment transfer direction; pull-side records reuse the same ledger."""

import sqlalchemy as sa

from alembic import op

revision = "20261009_0037"
down_revision = "20261009_0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bug_zentao_attachments",
        sa.Column(
            "direction",
            sa.String(20),
            nullable=False,
            server_default="push",
            comment="文件传输方向：push 平台推送上传到禅道 / pull 从禅道拉取导入到平台",
        ),
    )


def downgrade():
    op.drop_column("bug_zentao_attachments", "direction")

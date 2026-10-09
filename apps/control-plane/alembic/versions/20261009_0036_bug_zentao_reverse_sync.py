"""Express zentao reverse sync: link source/identity and per-group baselines.

Existing rows are backfilled with the stable instance hash so different MCP
endpoints pointing at one Zentao instance share one remote identity. The hash
helpers are pure URL functions imported here; no ORM models are involved.
"""

import sqlalchemy as sa

from alembic import op
from testing_agent.services.service_instance import instance_key

revision = "20261009_0036"
down_revision = "20261008_0035"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    op.add_column(
        "bug_zentao_pushes",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="push",
            comment="关联来源：push 平台推送创建 / import 禅道 Bug 导入",
        ),
    )
    op.add_column(
        "bug_zentao_pushes",
        sa.Column(
            "instance_key",
            sa.String(64),
            nullable=True,
            comment="实例地址的规范化哈希；跨端点识别同一禅道实例并支撑远端身份唯一约束",
        ),
    )
    op.add_column(
        "bug_zentao_pushes",
        sa.Column(
            "source_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("('{}')"),
            comment="远端来源快照 JSON：导入的原始 openedBy/openedDate/等级及拉取确认时的远端值；不含凭据",
        ),
    )
    rows = connection.execute(
        sa.text("SELECT id, instance_url FROM bug_zentao_pushes WHERE instance_key IS NULL")
    ).fetchall()
    for row_id, instance_url in rows:
        connection.execute(
            sa.text("UPDATE bug_zentao_pushes SET instance_key = :key WHERE id = :id"),
            {"key": instance_key(instance_url), "id": row_id},
        )
    # batch 模式：SQLite 无法直接 ALTER 出约束，MySQL 上仍等价于原生 ADD CONSTRAINT。
    with op.batch_alter_table("bug_zentao_pushes") as batch:
        batch.create_unique_constraint(
            "uk_bug_zentao_remote_identity", ["instance_key", "remote_bug_id"]
        )
    op.create_table(
        "bug_zentao_sync_baselines",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="数据库内部主键"
        ),
        sa.Column(
            "bug_id",
            sa.String(64),
            nullable=False,
            comment="平台 Bug 业务标识",
        ),
        sa.Column(
            "field_group",
            sa.String(20),
            nullable=False,
            comment="字段组标识：profile 基本信息 / description 描述 / status 状态 / assignee 责任人",
        ),
        sa.Column(
            "local_snapshot_json",
            sa.JSON(),
            nullable=False,
            comment="应用确认时刻的本地字段组值快照 JSON",
        ),
        sa.Column(
            "remote_snapshot_json",
            sa.JSON(),
            nullable=False,
            comment="应用确认时刻的远端字段组值快照 JSON",
        ),
        sa.Column(
            "operation_id",
            sa.String(64),
            nullable=False,
            comment="本轮确认应用的操作标识，用于结果核对与去重",
        ),
        sa.Column(
            "applied_by", sa.String(64), nullable=False, comment="确认应用的操作人用户业务标识"
        ),
        sa.Column("applied_at", sa.DateTime(), nullable=False, comment="基线确认应用时间（UTC）"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, comment="记录创建时间（UTC）"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录最后更新时间（UTC）",
        ),
        sa.ForeignKeyConstraint(["bug_id"], ["bugs.bug_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("bug_id", "field_group", name="uk_bug_zentao_baseline"),
        comment="Bug 禅道反向同步的字段组基线：最近一次确认应用时两端值快照",
    )


def downgrade():
    op.drop_table("bug_zentao_sync_baselines")
    with op.batch_alter_table("bug_zentao_pushes") as batch:
        batch.drop_constraint("uk_bug_zentao_remote_identity", type_="unique")
    op.drop_column("bug_zentao_pushes", "source_json")
    op.drop_column("bug_zentao_pushes", "instance_key")
    op.drop_column("bug_zentao_pushes", "source")

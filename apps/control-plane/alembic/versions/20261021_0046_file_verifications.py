"""Fence file verification and retain cleanup evidence across process loss."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0046"
down_revision = "20261021_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stored_files",
        sa.Column(
            "verification_id",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="当前核验代次；空表示尚未领取或已失败",
        ),
    )
    op.create_table(
        "file_verifications",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            comment="核验记录数据库内部主键",
        ),
        sa.Column("operation_id", sa.String(64), nullable=False, comment="本次核验唯一代次"),
        sa.Column("file_id", sa.String(64), nullable=False, comment="对应统一文件业务标识"),
        sa.Column("bucket", sa.String(255), nullable=False, comment="本次核验目标存储桶"),
        sa.Column(
            "object_key",
            sa.String(512),
            nullable=False,
            comment="本代次独占对象键；不得被其他代次复用",
        ),
        sa.Column(
            "state",
            sa.String(20),
            nullable=False,
            comment="核验状态：running/published/discarded/abandoned",
        ),
        sa.Column(
            "deadline",
            sa.DateTime(),
            nullable=False,
            comment="允许发布本次核验结果的截止时间（UTC）",
        ),
        sa.Column(
            "settled_at",
            sa.DateTime(),
            nullable=True,
            comment="确认本次存储调用已经结束的时间；空表示仍可能晚到写入",
        ),
        sa.Column(
            "gc_after",
            sa.DateTime(),
            nullable=False,
            comment="下次可领取回收的时间（UTC）；未确认结束的对象持续巡检",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, comment="核验领取时间（UTC）"
        ),
        sa.UniqueConstraint("operation_id"),
        comment="文件核验代次及未发布对象回收凭据；不随业务文件删除而级联丢失",
    )
    op.create_index("ix_file_verifications_file_id", "file_verifications", ["file_id"])
    op.create_index(
        "ix_file_verification_gc", "file_verifications", ["bucket", "state", "gc_after"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM file_verifications")):
        raise RuntimeError("Preserve verification and orphan cleanup evidence; downgrade refused")
    op.drop_table("file_verifications")
    op.drop_column("stored_files", "verification_id")

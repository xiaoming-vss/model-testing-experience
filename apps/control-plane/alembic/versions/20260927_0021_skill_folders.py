"""Replace obsolete archives with current folder manifests and global defaults."""

import sqlalchemy as sa

from alembic import op

revision = "20260927_0021"
down_revision = "20260927_0020"
branch_labels = None
depends_on = None


def upgrade():
    # Old archive skill data is explicitly discarded. Other business files are untouched.
    op.execute(
        "UPDATE stored_files SET status='deleting' WHERE purpose='project_skill' "
        "AND resource_type='project_skill'"
    )
    op.execute("DELETE FROM project_skill_spaces")
    # MySQL needs a separate project index before removing the old FK-supporting unique index.
    op.create_index("ix_project_skill_spaces_project_id", "project_skill_spaces", ["project_id"])
    with op.batch_alter_table("project_skill_spaces") as batch:
        batch.drop_constraint("uk_project_skill_filename", type_="unique")
        batch.alter_column("project_id", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("scope_key", sa.String(64), nullable=False))
        batch.add_column(sa.Column("manifest", sa.JSON(), nullable=False))
        batch.create_unique_constraint("uk_skill_scope_name", ["scope_key", "filename"])
        for name in ("version", "download_url", "file_id", "storage_path"):
            batch.drop_column(name)


def downgrade():
    # Schema round trips are supported for empty installations, never reinterpret folder data.
    if op.get_bind().execute(sa.text("SELECT count(*) FROM project_skill_spaces")).scalar():
        raise RuntimeError("技能库非空，不能降级为压缩包结构；请恢复备份")
    with op.batch_alter_table("project_skill_spaces") as batch:
        batch.drop_constraint("uk_skill_scope_name", type_="unique")
        batch.drop_column("manifest")
        batch.drop_column("scope_key")
        batch.alter_column("project_id", existing_type=sa.String(64), nullable=False)
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("download_url", sa.String(512), nullable=False))
        batch.add_column(sa.Column("storage_path", sa.String(512), nullable=False))
        batch.add_column(sa.Column("file_id", sa.String(64), nullable=False, server_default=""))
        batch.create_unique_constraint("uk_project_skill_filename", ["project_id", "filename"])
    op.drop_index("ix_project_skill_spaces_project_id", table_name="project_skill_spaces")

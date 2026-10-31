"""Separate API and UI environments and make variable keys case-sensitive."""

import sqlalchemy as sa

from alembic import op

revision = "20261028_0050"
down_revision = "20261021_0049"
branch_labels = None
depends_on = None


def _is_mysql() -> bool:
    return op.get_bind().dialect.name == "mysql"


def upgrade() -> None:
    op.add_column(
        "api_environments",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default="api",
            comment="环境用途：api / ui",
        ),
    )
    with op.batch_alter_table("api_environments") as batch:
        # 先建新唯一键再删旧键：MySQL 的 project_id 外键依赖旧键作为索引，
        # 中间不能出现 project_id 没有索引的瞬间。
        batch.create_unique_constraint(
            "uk_api_environment_project_kind_name",
            ["project_id", "kind", "name"],
        )
        batch.drop_constraint("uk_api_environment_project_name", type_="unique")

    if _is_mysql():
        # Rebuild the unique index around the column change so MySQL keeps a single index
        # definition with the new collation instead of leaving a stale one.
        op.drop_index("uk_api_env_var_key", table_name="api_environment_vars")
        op.execute(
            "ALTER TABLE api_environment_vars "
            "MODIFY var_key VARCHAR(120) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL "
            "COMMENT '变量名称；区分大小写'"
        )
        op.create_index(
            "uk_api_env_var_key",
            "api_environment_vars",
            ["environment_id", "var_key"],
            unique=True,
        )


def downgrade() -> None:
    if _is_mysql():
        connection = op.get_bind()
        table_collation = connection.scalar(
            sa.text(
                "SELECT TABLE_COLLATION FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'api_environment_vars'"
            )
        )
        # 回退会把排序规则改回大小写不敏感；先按目标规则检查会合并的变量名。
        duplicated_keys = connection.scalar(
            sa.text(
                "SELECT COUNT(*) FROM ("
                f"SELECT var_key COLLATE {table_collation} AS grouped_key "
                "FROM api_environment_vars "
                f"GROUP BY var_key COLLATE {table_collation} HAVING COUNT(*) > 1"
                ") AS duplicated"
            )
        )
        if duplicated_keys:
            raise RuntimeError(
                "Cannot restore case-insensitive variable keys while case-only duplicates exist"
            )
        op.drop_index("uk_api_env_var_key", table_name="api_environment_vars")
        op.execute(
            "ALTER TABLE api_environment_vars "
            f"MODIFY var_key VARCHAR(120) CHARACTER SET utf8mb4 COLLATE {table_collation} NOT NULL "
            "COMMENT '变量名称；区分大小写'"
        )
        op.create_index(
            "uk_api_env_var_key",
            "api_environment_vars",
            ["environment_id", "var_key"],
            unique=True,
        )

    # API and UI environments may share a name; the old constraint cannot hold both.
    duplicated_names = op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "SELECT project_id, name FROM api_environments "
            "GROUP BY project_id, name HAVING COUNT(*) > 1"
            ") AS duplicated"
        )
    )
    if duplicated_names:
        raise RuntimeError(
            "Cannot restore project-wide environment names while API and UI share a name"
        )
    with op.batch_alter_table("api_environments") as batch:
        # 先恢复旧唯一键再删新键，保证 project_id 始终有索引供外键使用。
        batch.create_unique_constraint(
            "uk_api_environment_project_name",
            ["project_id", "name"],
        )
        batch.drop_constraint("uk_api_environment_project_kind_name", type_="unique")
    op.drop_column("api_environments", "kind")

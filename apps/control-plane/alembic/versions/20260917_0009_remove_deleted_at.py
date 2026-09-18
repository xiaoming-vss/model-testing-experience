"""Remove soft-deletion columns and redundant indexes after the hard-delete cutover."""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0009"
down_revision = "20260917_0008"
branch_labels = None
depends_on = None

# Old index, old columns, optional replacement index, replacement columns.
TABLES = {
    "ai_generate_tasks": [
        (
            "ix_ai_generate_tasks_creator_user_id_deleted_at",
            ["creator_user_id", "deleted_at"],
            "ix_ai_generate_tasks_creator_user_id",
            ["creator_user_id"],
        ),
        (
            "ix_ai_generate_tasks_project_id_deleted_at",
            ["project_id", "deleted_at"],
            "ix_ai_generate_tasks_project_id",
            ["project_id"],
        ),
        (
            "ix_ai_generate_tasks_requirement_id_deleted_at",
            ["requirement_id", "deleted_at"],
            "ix_ai_generate_tasks_requirement_id",
            ["requirement_id"],
        ),
        (
            "ix_ai_generate_tasks_sprint_id_deleted_at",
            ["sprint_id", "deleted_at"],
            "ix_ai_generate_tasks_sprint_id",
            ["sprint_id"],
        ),
    ],
    "api_assert_rules": [
        ("ix_api_assert_rules_case_id_deleted_at", ["case_id", "deleted_at"], None, ["case_id"])
    ],
    "api_cases": [
        (
            "ix_api_cases_collection_id_deleted_at",
            ["collection_id", "deleted_at"],
            None,
            ["collection_id"],
        )
    ],
    "api_collections": [
        (
            "ix_api_collections_requirement_id_deleted_at",
            ["requirement_id", "deleted_at"],
            None,
            ["requirement_id"],
        )
    ],
    "api_environments": [
        (
            "ix_api_environments_project_id_deleted_at",
            ["project_id", "deleted_at"],
            None,
            ["project_id"],
        )
    ],
    "api_extract_rules": [
        ("ix_api_extract_rules_case_id_deleted_at", ["case_id", "deleted_at"], None, ["case_id"])
    ],
    "function_test_cases": [
        (
            "ix_function_test_cases_suite_id_deleted_at",
            ["suite_id", "deleted_at"],
            None,
            ["suite_id"],
        )
    ],
    "function_test_suites": [
        (
            "ix_function_test_suites_requirement_id_deleted_at",
            ["requirement_id", "deleted_at"],
            None,
            ["requirement_id"],
        )
    ],
    "integration_connections": [
        (
            "ix_integration_connections_project_id_deleted_at",
            ["project_id", "deleted_at"],
            "ix_integration_connections_project_id",
            ["project_id"],
        ),
        (
            "ix_integration_connections_user_id_deleted_at",
            ["user_id", "deleted_at"],
            None,
            ["user_id"],
        ),
    ],
    "projects": [("ix_projects_user_id_deleted_at", ["user_id", "deleted_at"], None, ["user_id"])],
    "project_skill_spaces": [
        (
            "ix_project_skill_spaces_project_id_deleted_at",
            ["project_id", "deleted_at"],
            None,
            ["project_id"],
        )
    ],
    "requirements": [
        ("ix_requirements_sprint_id_deleted_at", ["sprint_id", "deleted_at"], None, ["sprint_id"])
    ],
    "resource_bindings": [],
    "shared_services": [],
    "sprints": [
        ("ix_sprints_project_id_deleted_at", ["project_id", "deleted_at"], None, ["project_id"])
    ],
    "ui_test_cases": [
        ("ix_ui_test_cases_suite_id_deleted_at", ["suite_id", "deleted_at"], None, ["suite_id"])
    ],
    "ui_test_suites": [
        (
            "ix_ui_test_suites_requirement_id_deleted_at",
            ["requirement_id", "deleted_at"],
            None,
            ["requirement_id"],
        )
    ],
}


def upgrade():
    connection = op.get_bind()
    # Refuse to expose hidden legacy data: clean/archive it explicitly first.
    for table in TABLES:
        row = connection.execute(
            sa.text(f"SELECT 1 FROM {table} WHERE deleted_at IS NOT NULL LIMIT 1")
        ).first()
        if row is not None:
            raise RuntimeError(f"{table} still contains soft-deleted records; archive/clean first")
    for table, indexes in TABLES.items():
        # Create the replacement before dropping an index used by a MySQL FK.
        for _old, _columns, new, columns in indexes:
            if new:
                op.create_index(new, table, columns)
        with op.batch_alter_table(table) as batch:
            for old, _columns, _new, _new_columns in indexes:
                batch.drop_index(old)
            batch.drop_column("deleted_at")


def downgrade():
    for table, indexes in reversed(list(TABLES.items())):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
            for old, columns, _new, _new_columns in indexes:
                batch.create_index(old, columns)
        for _old, _columns, new, _new_columns in indexes:
            if new:
                op.drop_index(new, table_name=table)

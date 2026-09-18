"""Protect business hierarchy and ownership for hard deletion.

The initial schema remains frozen. Initialization runs through this revision.
"""

from alembic import op

revision = "20260917_0008"
down_revision = "20260916_0007"
branch_labels = None
depends_on = None

LINKS = [
    ("sprints", "project_id", "projects", "project_id", "RESTRICT"),
    ("function_test_cases", "suite_id", "function_test_suites", "suite_id", "RESTRICT"),
    ("ui_test_cases", "suite_id", "ui_test_suites", "suite_id", "RESTRICT"),
    ("api_environments", "project_id", "projects", "project_id", "RESTRICT"),
    ("project_skill_spaces", "project_id", "projects", "project_id", "RESTRICT"),
    ("ai_generate_tasks", "project_id", "projects", "project_id", "RESTRICT"),
    ("api_assert_rules", "case_id", "api_cases", "case_id", "CASCADE"),
    ("api_extract_rules", "case_id", "api_cases", "case_id", "CASCADE"),
    ("api_environment_vars", "environment_id", "api_environments", "environment_id", "CASCADE"),
    ("api_collection_runs", "collection_id", "api_collections", "collection_id", "CASCADE"),
    (
        "api_collection_run_items",
        "collection_run_id",
        "api_collection_runs",
        "collection_run_id",
        "CASCADE",
    ),
    ("api_collection_run_items", "case_id", "api_cases", "case_id", "CASCADE"),
    ("ui_test_case_runs", "case_id", "ui_test_cases", "case_id", "CASCADE"),
    ("ui_test_suite_runs", "suite_id", "ui_test_suites", "suite_id", "CASCADE"),
    ("ui_test_suite_run_items", "suite_run_id", "ui_test_suite_runs", "suite_run_id", "CASCADE"),
    ("ui_test_suite_run_items", "case_id", "ui_test_cases", "case_id", "CASCADE"),
    ("ai_generate_task_runs", "task_id", "ai_generate_tasks", "task_id", "CASCADE"),
    ("ai_generate_task_source_archives", "task_id", "ai_generate_tasks", "task_id", "CASCADE"),
]


def upgrade():
    for table, column, parent, key, behavior in LINKS:
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                f"fk_{table}_{column}", parent, [column], [key], ondelete=behavior
            )


def downgrade():
    for table, column, _parent, _key, _behavior in reversed(LINKS):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_{column}", type_="foreignkey")

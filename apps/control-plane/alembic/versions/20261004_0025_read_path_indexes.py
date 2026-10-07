"""Indexes for shared resource lists, AI history and newest execution per resource."""

from alembic import op

revision = "20261004_0025"
down_revision = "20261003_0024"
branch_labels = None
depends_on = None

INDEXES = [
    (
        "idx_ai_task_project_type_created",
        "ai_generate_tasks",
        ["project_id", "task_type", "created_at", "id"],
    ),
    ("idx_ai_run_task_created", "ai_generate_task_runs", ["task_id", "created_at", "id"]),
    (
        "idx_binding_shared_created",
        "resource_bindings",
        ["local_resource_type", "local_resource_id", "created_at", "id"],
    ),
    ("idx_bug_project_created", "bugs", ["project_id", "created_at", "id"]),
    ("idx_api_case_run_latest", "api_case_runs", ["case_id", "created_at", "id"]),
    ("idx_ui_case_run_latest", "ui_test_case_runs", ["case_id", "created_at", "id"]),
    ("idx_ui_suite_run_latest", "ui_test_suite_runs", ["suite_id", "created_at", "id"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)

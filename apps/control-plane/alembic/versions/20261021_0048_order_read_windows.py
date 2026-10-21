"""Page order summaries without loading entry bodies for step counts."""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0048"
down_revision = "20261021_0047"
branch_labels = None
depends_on = None

INDEXES = (
    ("idx_order_project_page", "test_orders", ["project_id", "created_at", "id"]),
    ("idx_order_sprint_page", "test_orders", ["project_id", "sprint_id", "created_at", "id"]),
    ("idx_order_entry_status_page", "test_order_entries", ["order_id", "status", "order_no", "id"]),
    (
        "idx_order_entry_assignee_page",
        "test_order_entries",
        ["order_id", "assignee_user_id", "order_no", "id"],
    ),
)


def upgrade() -> None:
    op.add_column(
        "test_order_entries",
        sa.Column(
            "step_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="冻结用例快照中的步骤条数；供摘要列表展示，随快照创建后保持不变",
        ),
    )
    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "UPDATE test_order_entries SET step_count = CASE "
            "WHEN JSON_TYPE(JSON_EXTRACT(snapshot_json, '$.steps')) = 'ARRAY' "
            "THEN JSON_LENGTH(JSON_EXTRACT(snapshot_json, '$.steps')) ELSE 0 END"
        )
    else:
        op.execute(
            "UPDATE test_order_entries SET step_count = CASE "
            "WHEN json_type(snapshot_json, '$.steps') = 'array' "
            "THEN json_array_length(snapshot_json, '$.steps') ELSE 0 END"
        )
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_column("test_order_entries", "step_count")

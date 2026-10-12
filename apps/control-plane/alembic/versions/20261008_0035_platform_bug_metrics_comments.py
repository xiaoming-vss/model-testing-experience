"""Describe platform Bug snapshots; preserve historical values and schema types."""

import sqlalchemy as sa

from alembic import op

revision = "20261008_0035"
down_revision = "20261007_0034"
branch_labels = None
depends_on = None

OLD = {
    "bug_metrics_collected": "本快照是否已采集禅道缺陷指标",
    "bug_details_json": "采集的禅道缺陷详细快照 JSON",
    "bug_total": "禅道缺陷总数",
    "bug_resolved": "禅道缺陷已解决数",
    "bug_closed": "禅道缺陷已关闭数",
    "bug_unresolved": "禅道缺陷未解决数",
    "bug_fatal": "禅道缺陷致命数",
    "bug_serious": "禅道缺陷严重数",
    "bug_normal": "禅道缺陷一般数",
    "bug_suggestion": "禅道缺陷建议数",
}
NEW = {
    "bug_metrics_collected": "本快照是否已成功统计缺陷；历史未采集为否",
    "bug_details_json": (
        "缺陷摘要快照 JSON；平台条目含 bugId/bugNo/title/status/severity/resolution，历史格式保留"
    ),
    "bug_total": "缺陷快照总数",
    "bug_resolved": "缺陷快照已解决数",
    "bug_closed": "缺陷快照已关闭数",
    "bug_unresolved": "缺陷快照未解决数",
    "bug_fatal": "缺陷快照致命数",
    "bug_serious": "缺陷快照严重数",
    "bug_normal": "缺陷快照一般数",
    "bug_suggestion": "缺陷快照轻微数；平台 minor 映射至历史 suggestion 字段",
}


def apply_comments(comments: dict[str, str]) -> None:
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        return
    columns = {c["name"]: c for c in sa.inspect(connection).get_columns("sprint_daily_metrics")}
    for name, comment in comments.items():
        column = columns[name]
        default = column["default"]
        op.alter_column(
            "sprint_daily_metrics",
            name,
            comment=comment,
            existing_comment=column.get("comment"),
            existing_type=column["type"],
            existing_nullable=column["nullable"],
            existing_server_default=sa.text(default) if default is not None else None,
            existing_autoincrement=column.get("autoincrement", False),
        )


def upgrade() -> None:
    apply_comments(NEW)


def downgrade() -> None:
    apply_comments(OLD)

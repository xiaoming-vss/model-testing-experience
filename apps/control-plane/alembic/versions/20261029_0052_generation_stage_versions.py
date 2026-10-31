"""Create approved stage versions and backfill historical approvals.

Versions are chain-private. A version copies the approved attempt content so a
later run deletion cannot erase an already approved artifact.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20261029_0052"
down_revision = "20261028_0051"
branch_labels = None
depends_on = None

_CONTENT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")

_KINDS = (
    "requirement_analysis",
    "functional_case_generate",
    "api_case_generate",
    "ui_case_generate",
)


def upgrade() -> None:
    op.create_table(
        "ai_generate_stage_versions",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            comment="数据库内部主键",
        ),
        sa.Column("version_id", sa.String(64), nullable=False, comment="阶段版本业务标识"),
        sa.Column(
            "task_id", sa.String(64), nullable=False, comment="阶段版本所属生成链任务业务标识"
        ),
        sa.Column("stage", sa.String(40), nullable=False, comment="阶段版本对应的 AI 阶段标识"),
        sa.Column(
            "version_no",
            sa.Integer(),
            nullable=False,
            comment="同一生成链同一阶段内从 1 开始递增的版本号",
        ),
        sa.Column("run_id", sa.String(64), nullable=False, comment="产生该版本的运行业务标识"),
        sa.Column(
            "attempt_id", sa.String(64), nullable=False, comment="产生该版本的阶段尝试主键标识"
        ),
        sa.Column(
            "artifact_content",
            _CONTENT,
            nullable=False,
            comment="审核通过时的阶段产物正文快照",
        ),
        sa.Column(
            "artifact_format",
            sa.String(20),
            nullable=False,
            comment="产物格式：json/text",
        ),
        sa.Column(
            "artifact_context_json",
            sa.JSON(),
            nullable=True,
            comment="审核通过时的阶段产物上下文 JSON",
        ),
        sa.Column(
            "upstream_versions_json",
            sa.JSON(),
            nullable=True,
            comment="生成该版本时读取的上游阶段及版本业务标识映射 JSON",
        ),
        sa.Column(
            "based_on_old",
            sa.Boolean(),
            nullable=False,
            comment="是否基于非最新上游版本审核通过",
        ),
        sa.Column(
            "reviewer_user_id",
            sa.String(64),
            nullable=False,
            comment="阶段审核人用户业务标识",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="阶段审核通过时间（UTC）",
        ),
        sa.Column("review_comment", sa.Text(), nullable=False, comment="阶段审核意见"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录创建时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["ai_generate_tasks.task_id"],
            name="fk_ai_stage_versions_task",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("version_id", name="uq_ai_stage_version_id"),
        sa.UniqueConstraint("task_id", "stage", "version_no", name="uq_ai_stage_version_number"),
        sa.UniqueConstraint("task_id", "stage", "attempt_id", name="uq_ai_stage_version_attempt"),
        comment="AI 生成链各阶段审核通过后形成的不可变版本及来源尝试快照",
    )
    op.create_index(
        "idx_ai_stage_version_chain",
        "ai_generate_stage_versions",
        ["task_id", "stage", "version_no"],
    )
    _backfill_versions()


def _backfill_versions() -> None:
    """Promote existing approved stage artifacts to v1..vN without touching runs."""
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text(
                """
                SELECT t.task_id, t.task_type, s.stage, s.run_id,
                       s.current_artifact_attempt_id, s.reviewer_user_id,
                       s.reviewed_at, s.review_comment, s.created_at,
                       a.output_content, a.output_format, a.output_context_json
                FROM ai_generate_run_stages s
                JOIN ai_generate_task_runs r ON r.run_id = s.run_id
                JOIN ai_generate_tasks t ON t.task_id = r.task_id
                JOIN ai_generate_stage_attempts a ON a.id = s.current_artifact_attempt_id
                WHERE s.review_status = 'approved'
                  AND a.output_content IS NOT NULL
                  AND t.task_type IN :kinds
                ORDER BY t.task_id, s.stage, COALESCE(s.reviewed_at, s.created_at), s.id
                """
            ).bindparams(sa.bindparam("kinds", expanding=True)),
            {"kinds": list(_KINDS)},
        ).mappings()
    )
    counters: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["task_id"], row["stage"])
        counters[key] = counters.get(key, 0) + 1
        reviewed_at = row["reviewed_at"] or row["created_at"] or datetime.now(UTC)
        raw_context = row["output_context_json"]
        if raw_context is None:
            artifact_context = None
        elif isinstance(raw_context, str):
            artifact_context = raw_context
        else:
            artifact_context = json.dumps(raw_context, ensure_ascii=False)
        connection.execute(
            sa.text(
                """
                INSERT INTO ai_generate_stage_versions (
                    version_id, task_id, stage, version_no, run_id, attempt_id,
                    artifact_content, artifact_format, artifact_context_json,
                    upstream_versions_json, based_on_old, reviewer_user_id,
                    reviewed_at, review_comment, created_at
                ) VALUES (
                    :version_id, :task_id, :stage, :version_no, :run_id, :attempt_id,
                    :artifact_content, :artifact_format, :artifact_context_json,
                    :upstream_versions_json, :based_on_old, :reviewer_user_id,
                    :reviewed_at, :review_comment, :created_at
                )
                """
            ),
            {
                "version_id": f"sv-{uuid4().hex}",
                "task_id": row["task_id"],
                "stage": row["stage"],
                "version_no": counters[key],
                "run_id": row["run_id"],
                "attempt_id": row["current_artifact_attempt_id"],
                "artifact_content": row["output_content"],
                "artifact_format": row["output_format"] or "text",
                "artifact_context_json": artifact_context,
                "upstream_versions_json": None,
                "based_on_old": False,
                "reviewer_user_id": row["reviewer_user_id"] or "",
                "reviewed_at": reviewed_at,
                "review_comment": row["review_comment"] or "",
                "created_at": reviewed_at,
            },
        )


def downgrade() -> None:
    # Approved versions are the source of truth for the new chain UI. Removing the
    # table discards that history; callers must export it before a downgrade.
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM ai_generate_stage_versions")):
        raise RuntimeError("Export approved stage versions before downgrade")
    op.drop_index("idx_ai_stage_version_chain", table_name="ai_generate_stage_versions")
    op.drop_table("ai_generate_stage_versions")

"""Record leaf-version import provenance and invalidate broken drafts.

Every formal target receives an effective import pointer. Import rows keep the
leaf version, its complete parent chain and the formal case IDs changed by that
import. Existing run-level imports are promoted where a historical leaf version
and complete parent chain can be reconstructed.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20261029_0053"
down_revision = "20261029_0052"
branch_labels = None
depends_on = None

_LEAF_STAGE = {
    "functional_case_generate": "detailed_cases",
    "api_case_generate": "generate",
    "ui_case_generate": "ui_yaml",
}

_UPSTREAMS = {
    "feature_understanding": ("extracting_text",),
    "case_names": ("requirement_analysis",),
    "detailed_cases": ("requirement_analysis", "case_names"),
    "ui_design": ("ui_surface",),
    "ui_yaml": ("ui_surface", "ui_design"),
    "generate": (),
}

_TARGET_TABLE = {
    "function_suite": ("function_test_suites", "suite_id"),
    "api_collection": ("api_collections", "collection_id"),
    "ui_suite": ("ui_test_suites", "suite_id"),
}


def upgrade() -> None:
    with op.batch_alter_table("ai_generate_stage_attempts") as batch:
        batch.add_column(
            sa.Column(
                "invalidated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="草稿因上游版本被删除而作废的时间（UTC）",
            )
        )
        batch.add_column(
            sa.Column(
                "invalidated_reason",
                sa.String(512),
                nullable=False,
                server_default="",
                comment="草稿作废原因",
            )
        )

    for table, _id_column in (
        ("function_test_suites", "suite_id"),
        ("api_collections", "collection_id"),
        ("ui_test_suites", "suite_id"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "effective_import_id",
                    sa.String(64),
                    nullable=True,
                    comment="当前正式来源的版本导入记录业务标识",
                )
            )
            batch.create_index(
                f"idx_{table}_effective_import", ["effective_import_id"], unique=False
            )

    op.create_table(
        "ai_generate_version_imports",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True, comment="数据库内部主键"
        ),
        sa.Column("import_id", sa.String(64), nullable=False, comment="导入记录业务标识"),
        sa.Column(
            "task_id", sa.String(64), nullable=False, comment="叶子版本所属生成链任务业务标识"
        ),
        sa.Column(
            "version_id", sa.String(64), nullable=False, comment="被导入的叶子阶段版本业务标识"
        ),
        sa.Column(
            "leaf_stage", sa.String(40), nullable=False, comment="被导入叶子版本对应的阶段标识"
        ),
        sa.Column(
            "target_type",
            sa.String(30),
            nullable=False,
            comment="正式目标类型：function_suite/api_collection/ui_suite",
        ),
        sa.Column("target_id", sa.String(64), nullable=False, comment="正式目标业务标识"),
        sa.Column(
            "parent_versions_json",
            mysql.JSON(),
            nullable=True,
            comment="叶子版本的完整上游阶段与版本标识映射 JSON",
        ),
        sa.Column(
            "changed_case_ids_json",
            mysql.JSON(),
            nullable=True,
            comment="本次导入新增或覆盖的正式用例业务标识列表 JSON",
        ),
        sa.Column(
            "target_case_count",
            sa.Integer(),
            nullable=False,
            comment="导入完成后正式目标内的用例总数",
        ),
        sa.Column(
            "mixed_source",
            sa.Boolean(),
            nullable=False,
            comment="正式目标是否仍有本次导入未覆盖的旧来源用例",
        ),
        sa.Column(
            "reviewer_user_id",
            sa.String(64),
            nullable=False,
            comment="叶子版本审核人用户业务标识",
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="叶子版本审核通过时间（UTC）",
        ),
        sa.Column("review_comment", sa.Text(), nullable=False, comment="叶子版本审核意见"),
        sa.Column("imported_by", sa.String(64), nullable=False, comment="执行导入的用户业务标识"),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="正式资产导入时间（UTC）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="记录创建时间（UTC）",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["ai_generate_tasks.task_id"],
            name="fk_ai_version_import_task",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["ai_generate_stage_versions.version_id"],
            name="fk_ai_version_import_version",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("import_id", name="uq_ai_version_import_id"),
        comment="已通过叶子版本导入正式资产的来源、父链和变更用例记录",
    )
    op.create_index(
        "idx_ai_version_import_leaf",
        "ai_generate_version_imports",
        ["task_id", "version_id"],
    )
    op.create_index(
        "idx_ai_version_import_target",
        "ai_generate_version_imports",
        ["target_type", "target_id", "imported_at"],
    )
    _backfill_run_imports()


def _json_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _datetime_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _backfill_run_imports() -> None:
    connection = op.get_bind()
    versions = list(
        connection.execute(
            sa.text(
                """
                SELECT task_id, stage, version_id, version_no, run_id,
                       upstream_versions_json, v.reviewer_user_id,
                       v.reviewed_at, v.review_comment, v.created_at
                FROM ai_generate_stage_versions v
                ORDER BY task_id, stage, version_no
                """
            )
        ).mappings()
    )
    if not versions:
        return
    by_task_stage: dict[tuple[str, str], list[dict]] = {}
    by_id: dict[str, dict] = {}
    for row in versions:
        item = dict(row)
        item["upstream"] = _json_value(item.get("upstream_versions_json")) or {}
        item["reviewed"] = _datetime_value(item.get("reviewed_at") or item.get("created_at"))
        by_task_stage.setdefault((item["task_id"], item["stage"]), []).append(item)
        by_id[item["version_id"]] = item

    imports = list(
        connection.execute(
            sa.text(
                """
                SELECT i.id, i.run_id, i.imported_at, i.created_at,
                       i.imported_targets_json, r.task_id, t.task_type
                FROM ai_generate_run_imports i
                JOIN ai_generate_task_runs r ON r.run_id = i.run_id
                JOIN ai_generate_tasks t ON t.task_id = r.task_id
                ORDER BY COALESCE(i.imported_at, i.created_at), i.id
                """
            )
        ).mappings()
    )
    for row in imports:
        leaf_stage = _LEAF_STAGE.get(row["task_type"])
        if leaf_stage is None:
            continue
        candidates = by_task_stage.get((row["task_id"], leaf_stage), [])
        leaf = next((item for item in candidates if item["run_id"] == row["run_id"]), None)
        if leaf is None:
            continue
        parents = _complete_parent_chain(leaf, by_task_stage, by_id)
        if parents is None:
            continue
        targets = _json_value(row.get("imported_targets_json")) or []
        imported_at = _datetime_value(row.get("imported_at") or row.get("created_at"))
        if imported_at is None:
            continue
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_type = str(target.get("targetType") or target.get("target_type") or "")
            target_id = str(target.get("targetId") or target.get("target_id") or "")
            table_and_id = _TARGET_TABLE.get(target_type)
            if not target_id or table_and_id is None:
                continue
            table, id_column = table_and_id
            exists = connection.scalar(
                sa.text(f"SELECT COUNT(*) FROM {table} WHERE {id_column} = :target_id"),
                {"target_id": target_id},
            )
            if not exists:
                continue
            import_id = f"vi-legacy-{uuid4().hex}"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO ai_generate_version_imports (
                        import_id, task_id, version_id, leaf_stage, target_type,
                        target_id, parent_versions_json, changed_case_ids_json,
                        target_case_count, mixed_source, reviewer_user_id,
                        reviewed_at, review_comment, imported_by, imported_at,
                        created_at
                    ) VALUES (
                        :import_id, :task_id, :version_id, :leaf_stage, :target_type,
                        :target_id, :parent_versions_json, :changed_case_ids_json,
                        :target_case_count, :mixed_source, :reviewer_user_id,
                        :reviewed_at, :review_comment, :imported_by, :imported_at,
                        :created_at
                    )
                    """
                ),
                {
                    "import_id": import_id,
                    "task_id": row["task_id"],
                    "version_id": leaf["version_id"],
                    "leaf_stage": leaf_stage,
                    "target_type": target_type,
                    "target_id": target_id,
                    "parent_versions_json": json.dumps(parents, ensure_ascii=False),
                    "changed_case_ids_json": "[]",
                    "target_case_count": 0,
                    "mixed_source": False,
                    "reviewer_user_id": leaf.get("reviewer_user_id") or "",
                    "reviewed_at": leaf.get("reviewed_at"),
                    "review_comment": leaf.get("review_comment") or "",
                    "imported_by": "",
                    "imported_at": imported_at,
                    "created_at": imported_at,
                },
            )
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET effective_import_id = :import_id "
                    f"WHERE {id_column} = :target_id"
                ),
                {"import_id": import_id, "target_id": target_id},
            )


def _complete_parent_chain(leaf, by_task_stage, by_id):
    parents: dict[str, str] = {}
    visiting: set[str] = set()

    def walk(version: dict) -> bool:
        stage = version["stage"]
        if stage in visiting:
            return False
        visiting.add(stage)
        for upstream_stage in _UPSTREAMS.get(stage, ()):
            if upstream_stage in parents:
                continue
            upstream_id = str(version["upstream"].get(upstream_stage) or "")
            if upstream_id:
                upstream = by_id.get(upstream_id)
                if upstream is None or upstream.get("stage") != upstream_stage:
                    return False
            else:
                candidates = by_task_stage.get((version["task_id"], upstream_stage), [])
                cutoff = version.get("reviewed")
                upstream = next(
                    (
                        item
                        for item in reversed(candidates)
                        if cutoff is None
                        or item.get("reviewed") is None
                        or item["reviewed"] <= cutoff
                    ),
                    None,
                )
                if upstream is None:
                    return False
            parents[upstream_stage] = upstream["version_id"]
            if not walk(upstream):
                return False
        visiting.discard(stage)
        return True

    return parents if walk(leaf) else None


def downgrade() -> None:
    # Dropping the table discards import provenance; formal assets remain.
    op.drop_index("idx_ai_version_import_target", table_name="ai_generate_version_imports")
    op.drop_index("idx_ai_version_import_leaf", table_name="ai_generate_version_imports")
    op.drop_table("ai_generate_version_imports")
    for table in ("ui_test_suites", "api_collections", "function_test_suites"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"idx_{table}_effective_import")
            batch.drop_column("effective_import_id")
    with op.batch_alter_table("ai_generate_stage_attempts") as batch:
        batch.drop_column("invalidated_reason")
        batch.drop_column("invalidated_at")

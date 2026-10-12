"""Drop write-only residue columns left by past feature migrations.

All removed columns were verified to have no readers in control-plane, workers
or studio; see ADR 0008. Downgrade reconstructs the columns but cannot restore
the historical values that upgrade removed.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261010_0038"
down_revision = "20261009_0037"
branch_labels = None
depends_on = None

# MySQL truncates this FK name (naming convention output exceeds 64 characters);
# SQLite keeps the full convention name.
IMPORT_ARTIFACT_FK_MYSQL = "fk_ai_generate_run_imports_artifact_attempt_id_ai_genera_a821"
IMPORT_ARTIFACT_FK_SQLITE = (
    "fk_ai_generate_run_imports_artifact_attempt_id_ai_generate_stage_attempts"
)

DROPS = [
    # MySQL rejects plain defaults on TEXT/JSON; nullable=False columns get the
    # implicit type default when rows exist.
    ("ai_generate_task_source_archives", "storage_path", sa.Text(), True, None),
    ("sprint_daily_metrics", "metric_id", sa.String(64), False, None),
    ("integration_jobs", "claim_request_id", sa.String(64), True, ""),
    ("integration_claim_receipts", "worker_id", sa.String(128), True, ""),
    ("integration_job_steps", "input_digest", sa.String(64), True, ""),
    ("integration_restore_reviews", "facts_json", sa.JSON(), True, None),
    ("bug_zentao_sync_baselines", "applied_by", sa.String(64), True, ""),
    ("bug_zentao_pushes", "source_json", sa.JSON(), True, "{}"),
    ("requirements", "document_storage_path", sa.String(512), True, ""),
]


def upgrade():
    is_mysql = op.get_bind().dialect.name == "mysql"
    with op.batch_alter_table("ai_generate_run_imports") as batch:
        if is_mysql:
            batch.drop_constraint(IMPORT_ARTIFACT_FK_MYSQL, type_="foreignkey")
        batch.drop_column("artifact_attempt_id")
        batch.drop_column("imported_by")
        batch.drop_column("idempotency_key")
    if is_mysql:
        op.execute("ALTER TABLE ai_generate_run_imports COMMENT = 'AI 运行产物导入正式资产的记录'")
    for table, column, *_ in DROPS:
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column)


def downgrade():
    is_mysql = op.get_bind().dialect.name == "mysql"
    artifact_fk = IMPORT_ARTIFACT_FK_MYSQL if is_mysql else IMPORT_ARTIFACT_FK_SQLITE
    with op.batch_alter_table("ai_generate_run_imports") as batch:
        batch.add_column(sa.Column("imported_by", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "artifact_attempt_id",
                sa.String(64),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("idempotency_key", sa.String(128), nullable=True))
        batch.create_foreign_key(
            artifact_fk,
            "ai_generate_stage_attempts",
            ["artifact_attempt_id"],
            ["id"],
        )
    # Restore distinct placeholders before rebuilding the constraints. Historical
    # keys cannot be recovered, but import identity and row counts must survive.
    imports = sa.table(
        "ai_generate_run_imports",
        sa.column("id", sa.String(64)),
        sa.column("idempotency_key", sa.String(128)),
    )
    op.execute(imports.update().values(idempotency_key=sa.literal("restored:") + imports.c.id))
    with op.batch_alter_table("ai_generate_run_imports") as batch:
        batch.alter_column("idempotency_key", existing_type=sa.String(128), nullable=False)
        batch.create_unique_constraint(
            "uq_ai_generate_run_imports_idempotency_key", ["idempotency_key"]
        )
    if is_mysql:
        op.execute(
            "ALTER TABLE ai_generate_run_imports"
            " COMMENT = 'AI 运行产物导入正式资产的记录及幂等依据'"
        )
    for table, column, type_, notnull, server_default in reversed(DROPS):
        if column == "source_json":
            # MySQL only accepts expression defaults on JSON columns.
            server_default = sa.text("('{}')")
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    column,
                    type_,
                    nullable=True,
                    server_default=server_default,
                )
            )
        if notnull:
            # Populate TEXT/JSON explicitly; implicit defaults are not portable.
            restored = sa.table(table, sa.column(column, type_))
            op.execute(
                restored.update()
                .where(restored.c[column].is_(None))
                .values({column: {} if isinstance(type_, sa.JSON) else ""})
            )
            with op.batch_alter_table(table) as batch:
                batch.alter_column(column, existing_type=type_, nullable=False)
        if column == "metric_id":
            with op.batch_alter_table(table) as batch:
                batch.create_unique_constraint("uq_sprint_daily_metrics_metric_id", ["metric_id"])

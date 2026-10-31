"""Historical approved artifacts become v1 without changing the source ledger."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session
from support.initial_schema_migration import (
    compile_longtext_for_sqlite,  # noqa: F401
    migration_config,
)

from alembic import command
from testing_agent.models.ai_generate_execution import AiGenerateRunImport, AiGenerateRunStage
from testing_agent.models.ai_generate_stage_version import AiGenerateStageVersion
from testing_agent.models.ai_generate_task import AiGenerateTask, AiGenerateTaskRun
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.models.user import User


def test_upgrade_backfills_approved_stage_versions(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        command.upgrade(migration_config(connection), "20261028_0051")
        connection.commit()
    with Session(engine) as session:
        session.add(User(user_id="u", nickname="u"))
        session.flush()
        session.add(Project(project_id="p", user_id="u", name="p"))
        session.flush()
        session.add(
            Sprint(
                sprint_id="s",
                project_id="p",
                name="s",
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC) + timedelta(days=1),
            )
        )
        session.flush()
        session.add(Requirement(requirement_id="r", sprint_id="s", name="r"))
        session.flush()
        session.add(
            AiGenerateTask(
                task_id="task",
                task_type="functional_case_generate",
                name="task",
                project_id="p",
                sprint_id="s",
                requirement_id="r",
                creator_user_id="u",
                source_type="text",
                source_content="source",
                instruction="",
            )
        )
        session.flush()
        session.add(
            AiGenerateTaskRun(
                run_id="run",
                task_id="task",
                trigger_user_id="u",
                status="success",
                checkpoint_enabled=True,
                current_stage="requirement_analysis",
            )
        )
        session.flush()
        session.add(
            AiGenerateRunStage(
                id="stage",
                run_id="run",
                stage="requirement_analysis",
                stage_order=0,
                execution_status="success",
                review_status="approved",
                current_artifact_attempt_id="attempt",
                reviewer_user_id="u",
                review_comment="通过",
            )
        )
        session.flush()
        # This baseline predates draft invalidation; insert the historical row with
        # the columns that existed then instead of today's ORM mapping.
        session.execute(
            sa.text(
                """
                INSERT INTO ai_generate_stage_attempts (
                    id, stage_id, attempt_no, operation, status,
                    output_content, output_format, created_at
                ) VALUES (
                    'attempt', 'stage', 1, 'generate', 'success',
                    '{"purpose":"登录"}', 'json', :created_at
                )
                """
            ),
            {"created_at": datetime.now(UTC)},
        )
        session.commit()
    with engine.connect() as connection:
        command.upgrade(migration_config(connection), "head")
        connection.commit()
        row = (
            connection.execute(sa.text("SELECT * FROM ai_generate_stage_versions")).mappings().one()
        )
        assert row["task_id"] == "task"
        assert row["stage"] == "requirement_analysis"
        assert row["version_no"] == 1
        assert row["attempt_id"] == "attempt"
        assert row["artifact_content"] == '{"purpose":"登录"}'
        assert row["reviewer_user_id"] == "u"
    engine.dispose()


def test_upgrade_backfills_import_provenance_and_effective_target(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'import-migration.sqlite'}")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        command.upgrade(migration_config(connection), "20261029_0052")
        connection.commit()
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(User(user_id="u", nickname="u"))
        session.flush()
        session.add(Project(project_id="p", user_id="u", name="p"))
        session.flush()
        session.add(
            Sprint(
                sprint_id="s",
                project_id="p",
                name="s",
                start_time=now,
                end_time=now + timedelta(days=1),
            )
        )
        session.flush()
        session.add(Requirement(requirement_id="r", sprint_id="s", name="r"))
        session.flush()
        session.add(
            AiGenerateTask(
                task_id="task",
                task_type="functional_case_generate",
                name="task",
                project_id="p",
                sprint_id="s",
                requirement_id="r",
                creator_user_id="u",
                source_type="text",
                source_content="source",
                instruction="",
            )
        )
        session.flush()
        session.add(
            AiGenerateTaskRun(
                run_id="run",
                task_id="task",
                trigger_user_id="u",
                status="success",
                checkpoint_enabled=True,
                current_stage="detailed_cases",
            )
        )
        session.flush()
        session.execute(
            sa.text(
                """
                INSERT INTO function_test_suites (
                    suite_id, requirement_id, name, description, created_at, updated_at
                ) VALUES ('suite-1', 'r', '登录', '', :now, :now)
                """
            ),
            {"now": now},
        )
        versions = [
            ("sv-ra", "requirement_analysis", 1, {}),
            ("sv-cn", "case_names", 1, {"requirement_analysis": "sv-ra"}),
            (
                "sv-leaf",
                "detailed_cases",
                1,
                {"requirement_analysis": "sv-ra", "case_names": "sv-cn"},
            ),
        ]
        for index, (version_id, stage, version_no, upstream) in enumerate(versions):
            session.add(
                AiGenerateStageVersion(
                    version_id=version_id,
                    task_id="task",
                    stage=stage,
                    version_no=version_no,
                    run_id="run",
                    attempt_id=f"attempt-{index}",
                    artifact_content="cases: []",
                    artifact_format="yaml",
                    upstream_versions_json=upstream,
                    based_on_old=False,
                    reviewer_user_id="u",
                    reviewed_at=now + timedelta(minutes=index + 1),
                    review_comment="通过",
                    created_at=now + timedelta(minutes=index + 1),
                )
            )
        session.add(
            AiGenerateRunImport(
                id="import-1",
                run_id="run",
                imported_at=now + timedelta(minutes=5),
                imported_targets_json=[{"targetType": "function_suite", "targetId": "suite-1"}],
                created_at=now + timedelta(minutes=5),
            )
        )
        session.commit()
    with engine.connect() as connection:
        command.upgrade(migration_config(connection), "head")
        connection.commit()
        record = (
            connection.execute(sa.text("SELECT * FROM ai_generate_version_imports"))
            .mappings()
            .one()
        )
        assert record["version_id"] == "sv-leaf"
        assert record["leaf_stage"] == "detailed_cases"
        assert record["target_type"] == "function_suite"
        assert record["target_id"] == "suite-1"
        parent_versions = record["parent_versions_json"]
        if isinstance(parent_versions, str):
            import json

            parent_versions = json.loads(parent_versions)
        assert parent_versions == {
            "requirement_analysis": "sv-ra",
            "case_names": "sv-cn",
        }
        effective = connection.scalar(
            sa.text(
                "SELECT effective_import_id FROM function_test_suites WHERE suite_id = 'suite-1'"
            )
        )
        assert effective == record["import_id"]
    engine.dispose()

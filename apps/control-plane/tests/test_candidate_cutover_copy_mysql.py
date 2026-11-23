"""Exercise the offline cutover only against disposable MySQL databases."""

import importlib.util
import re
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from support.mysql_initialization import mysql, seed_row  # noqa: F401

from testing_agent.db.base import Base
from testing_agent.models.api_case import ApiCase
from testing_agent.models.api_collection import ApiCollection
from testing_agent.models.function_test_case import FunctionTestCase
from testing_agent.models.function_test_suite import FunctionTestSuite
from testing_agent.models.ui_test_case import UiTestCase
from testing_agent.models.ui_test_suite import UiTestSuite
from testing_agent.models.worker_task import WorkerTask

spec = importlib.util.spec_from_file_location(
    "candidate_cutover_copy", Path(__file__).parents[1] / "scripts/candidate_cutover_copy.py"
)
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)


def test_cutover_preserves_assets_and_rolls_back_on_failure(mysql, monkeypatch):  # noqa: F811
    db_name = f"candidate_copy_{uuid4().hex[:12]}_test"
    admin = sa.create_engine(mysql.url.set(database=None))
    source = sa.create_engine(mysql.url.set(database=db_name))
    with mysql.connect() as conn:
        database_collation = conn.scalar(sa.text("SELECT @@collation_database"))
    assert re.fullmatch(r"utf8mb4_[a-zA-Z0-9_]+", database_collation)
    with admin.begin() as conn:
        conn.exec_driver_sql(
            f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE {database_collation}"
        )
    try:
        Base.metadata.create_all(source)
        with mysql.connect() as target, source.begin() as conn:
            bootstrap = target.execute(sa.text("SELECT * FROM auth_runtime")).mappings().one()
            table = Base.metadata.tables["auth_runtime"]
            conn.execute(table.insert().values(**bootstrap))
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            for name in cutover.NEW_TABLES:
                conn.exec_driver_sql(f"DROP TABLE `{name}`")
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            for name in cutover.OLD_TABLES:
                conn.exec_driver_sql(f"CREATE TABLE `{name}` (id INTEGER PRIMARY KEY)")
            conn.exec_driver_sql(
                "ALTER TABLE ai_generation_stages ADD COLUMN next_version_no INTEGER NOT NULL "
                "DEFAULT 1, ADD COLUMN source_batch_id VARCHAR(64), "
                "ADD COLUMN source_snapshot_json JSON"
            )
            suite = seed_row(conn, FunctionTestSuite.__table__, {"effective_import_id": "old-f"})
            functional = seed_row(conn, FunctionTestCase.__table__, {"suite_id": suite["suite_id"]})
            collection = seed_row(conn, ApiCollection.__table__, {"effective_import_id": "old-a"})
            api_case = seed_row(
                conn, ApiCase.__table__, {"collection_id": collection["collection_id"]}
            )
            ui_suite = seed_row(conn, UiTestSuite.__table__, {"effective_import_id": "old-u"})
            ui_case = seed_row(conn, UiTestCase.__table__, {"suite_id": ui_suite["suite_id"]})
            conn.exec_driver_sql("ALTER TABLE function_test_cases AUTO_INCREMENT = 10000")
        with pytest.raises(ValueError, match="same database"):
            cutover.copy_database(source, source)
        with source.begin() as conn:
            queued = seed_row(conn, WorkerTask.__table__, {"status": "pending"})
        with pytest.raises(ValueError, match="Active execution must be resolved"):
            cutover.copy_database(source, mysql)
        with source.begin() as conn:
            conn.execute(sa.delete(WorkerTask).where(WorkerTask.id == queued["id"]))
        with mysql.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE auth_runtime ENGINE=MyISAM")
        try:
            with pytest.raises(ValueError, match="not transactional"):
                cutover.copy_database(source, mysql)
        finally:
            with mysql.begin() as conn:
                conn.exec_driver_sql("ALTER TABLE auth_runtime ENGINE=InnoDB")
        with mysql.begin() as conn:
            conn.exec_driver_sql("UPDATE auth_runtime SET fingerprint='do-not-overwrite'")
        with pytest.raises(ValueError, match="singleton is not the baseline"):
            cutover.copy_database(source, mysql)
        with mysql.begin() as conn:
            fingerprint = conn.scalar(sa.text("SELECT fingerprint FROM auth_runtime"))
            assert fingerprint == "do-not-overwrite"
            conn.exec_driver_sql("UPDATE auth_runtime SET fingerprint=''")
        with mysql.connect() as conn:
            target_collation = conn.scalar(
                sa.text(
                    "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='function_test_cases' "
                    "AND COLUMN_NAME='title'"
                )
            )
        assert re.fullmatch(r"utf8mb4_[a-zA-Z0-9_]+", target_collation)
        different_collation = (
            "utf8mb4_bin" if target_collation != "utf8mb4_bin" else "utf8mb4_unicode_ci"
        )
        with source.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE function_test_cases MODIFY title VARCHAR(255) "
                f"CHARACTER SET utf8mb4 COLLATE {different_collation} NOT NULL"
            )
        with pytest.raises(ValueError, match="Column type or nullability differs"):
            cutover.copy_database(source, mysql)
        with source.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE function_test_cases MODIFY title VARCHAR(255) "
                f"CHARACTER SET utf8mb4 COLLATE {target_collation} NOT NULL"
            )
        original_feed = cutover.feed
        calls = 0

        def fail_during_copy(digest, row):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise RuntimeError("injected")
            return original_feed(digest, row)

        monkeypatch.setattr(cutover, "feed", fail_during_copy)
        with pytest.raises(RuntimeError, match="injected"):
            cutover.copy_database(source, mysql)
        with mysql.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase)) == 0
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM auth_runtime")) == 1
            assert conn.scalar(sa.text("SELECT @@FOREIGN_KEY_CHECKS")) == 1
        with mysql.begin() as conn:
            conn.exec_driver_sql(
                "CREATE INDEX unexpected_cutover_index ON ai_generation_candidates (created_at)"
            )
        try:
            with pytest.raises(ValueError, match="schema does not match"):
                cutover.copy_database(source, mysql)
        finally:
            with mysql.begin() as conn:
                conn.exec_driver_sql(
                    "DROP INDEX unexpected_cutover_index ON ai_generation_candidates"
                )

        changed = False

        def change_source_during_copy(digest, row):
            nonlocal changed
            if not changed:
                changed = True
                with source.begin() as conn:
                    conn.execute(
                        sa.update(FunctionTestCase)
                        .where(FunctionTestCase.case_id == functional["case_id"])
                        .values(title="concurrent change")
                    )
            return original_feed(digest, row)

        monkeypatch.setattr(cutover, "feed", change_source_during_copy)
        with pytest.raises(ValueError, match="Source changed during copy"):
            cutover.copy_database(source, mysql)
        with mysql.connect() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(FunctionTestCase)) == 0
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM auth_runtime")) == 1
        with source.begin() as conn:
            conn.execute(
                sa.update(FunctionTestCase)
                .where(FunctionTestCase.case_id == functional["case_id"])
                .values(title=functional["title"])
            )
        monkeypatch.setattr(cutover, "feed", original_feed)
        table_count, row_count = cutover.copy_database(source, mysql)
        assert table_count > 50 and row_count >= 7
        with mysql.connect() as conn:
            next_id = conn.scalar(
                sa.text(
                    "SELECT AUTO_INCREMENT FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='function_test_cases'"
                )
            )
            assert next_id >= 10000
            assert (
                conn.execute(
                    sa.select(FunctionTestCase.title).where(
                        FunctionTestCase.case_id == functional["case_id"]
                    )
                ).scalar_one()
                == functional["title"]
            )
            assert (
                conn.execute(
                    sa.select(ApiCase.name).where(ApiCase.case_id == api_case["case_id"])
                ).scalar_one()
                == api_case["name"]
            )
            assert (
                conn.execute(
                    sa.select(UiTestCase.name).where(UiTestCase.case_id == ui_case["case_id"])
                ).scalar_one()
                == ui_case["name"]
            )
            for model in (FunctionTestSuite, ApiCollection, UiTestSuite):
                assert conn.scalar(sa.select(model.effective_import_id)) is None
        with pytest.raises(ValueError, match="not empty"):
            cutover.copy_database(source, mysql)
    finally:
        source.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP DATABASE `{db_name}`")
        admin.dispose()

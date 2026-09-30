"""Exercise the destructive archive-to-folder transition on an isolated database."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migration_discards_only_old_skill_data():
    path = Path(__file__).parents[1] / "alembic/versions/20260927_0021_skill_folders.py"
    spec = importlib.util.spec_from_file_location("skill_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE projects (project_id VARCHAR(64) PRIMARY KEY)")
        conn.exec_driver_sql(
            "CREATE TABLE stored_files (file_id VARCHAR(64), purpose VARCHAR(32), "
            "resource_type VARCHAR(32), status VARCHAR(20))"
        )
        conn.exec_driver_sql(
            "INSERT INTO stored_files VALUES "
            "('old', 'project_skill', 'project_skill', 'attached'), "
            "('req', 'requirement', 'requirement', 'attached')"
        )
        conn.exec_driver_sql("""CREATE TABLE project_skill_spaces (
            id INTEGER PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
            filename VARCHAR(255), version INTEGER, download_url VARCHAR(512),
            file_id VARCHAR(64), storage_path VARCHAR(512),
            CONSTRAINT uk_project_skill_filename UNIQUE (project_id, filename),
            CONSTRAINT fk_project_skill_spaces_project_id FOREIGN KEY(project_id)
            REFERENCES projects(project_id))""")
        conn.exec_driver_sql("INSERT INTO projects VALUES ('p')")
        conn.exec_driver_sql(
            "INSERT INTO project_skill_spaces (id, project_id, filename) VALUES (1, 'p', 'old.zip')"
        )
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert conn.exec_driver_sql("SELECT count(*) FROM project_skill_spaces").scalar() == 0
        assert dict(conn.exec_driver_sql("SELECT file_id, status FROM stored_files").all()) == {
            "old": "deleting",
            "req": "attached",
        }
        columns = {c["name"]: c for c in sa.inspect(conn).get_columns("project_skill_spaces")}
        assert columns["project_id"]["nullable"]
        assert "manifest" in columns and "scope_key" in columns
        assert "version" not in columns and "file_id" not in columns

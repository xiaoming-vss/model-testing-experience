"""Offline copy of an old MySQL database to a separate initialized candidate baseline.

All writers must remain stopped; a backup must have been independently restored and
verified. This command does not create databases, modify the source, or switch services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, Table, and_, create_engine, inspect, select, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool

import testing_agent.models  # noqa: F401
from testing_agent.core.config import load_settings
from testing_agent.db.base import Base

OLD_TABLES = {"ai_generate_stage_versions", "ai_generate_version_imports"}
NEW_TABLES = {
    "ai_generate_import_requests",
    "ai_generate_imports",
    "ai_generation_candidates",
    "ai_generation_review_receipts",
    "ai_generation_stage_contents",
    "requirement_generation_chains",
}
OLD_COLUMNS = {"next_version_no", "source_batch_id", "source_snapshot_json"}
TARGETS = {"function_test_suites", "api_collections", "ui_test_suites"}
ACTIVE_STATES = {
    "worker_tasks": ("pending", "queued", "claimed", "running", "stopping"),
    "integration_jobs": ("queued", "claimed", "running"),
    "perf_runs": ("queued", "running", "stopping"),
    "perf_suite_runs": ("queued", "running", "stopping"),
    "ai_generation_attempts": ("pending", "claimed", "running"),
}


def make_engine(path: Path) -> Engine:
    if not path.is_file():
        raise ValueError("Configuration file does not exist")
    url = make_url(load_settings(path).database_url)
    if not url.drivername.startswith("mysql") or not url.database:
        raise ValueError("Configuration must identify a MySQL database")
    return create_engine(url.set(drivername="mysql+pymysql"), poolclass=NullPool)


def feed(digest: Any, row: dict[str, Any]) -> None:
    def convert(value: Any) -> str:
        if isinstance(value, (datetime, date, Decimal)):
            return str(value)
        if isinstance(value, bytes):
            return value.hex()
        raise TypeError(f"Unsupported data type: {type(value).__name__}")

    data = json.dumps(row, sort_keys=True, ensure_ascii=False, default=convert).encode()
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)


def snapshot(conn: Connection) -> None:
    conn.exec_driver_sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    conn.exec_driver_sql("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")


def rows(conn: Connection, table: Table, columns: list[str], keys: list[str]):
    query = select(*(table.c[name] for name in columns)).order_by(*(table.c[k] for k in keys))
    return conn.execution_options(stream_results=True).execute(query).mappings()


def column_collations(conn: Connection) -> dict[tuple[str, str], str | None]:
    query = text(
        "SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE()"
    )
    return {(table, column): collation for table, column, collation in conn.execute(query)}


def require_transactional_tables(conn: Connection) -> None:
    query = text(
        "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'"
    )
    for table, engine in conn.execute(query):
        if engine is None or engine.lower() != "innodb":
            raise ValueError(f"Table is not transactional: {table}")


def prepare(
    src: Connection, dst: Connection
) -> dict[str, tuple[Table, Table, list[str], list[str]]]:
    require_transactional_tables(src)
    require_transactional_tables(dst)
    old_names = set(inspect(src).get_table_names()) - {"alembic_version"}
    new_names = set(inspect(dst).get_table_names()) - {"alembic_version"}
    if new_names != set(Base.metadata.tables) or new_names - old_names != NEW_TABLES:
        raise ValueError("Unexpected target or missing source tables")
    if old_names - new_names != OLD_TABLES:
        raise ValueError("Unexpected extra source tables")
    for table_name, active_states in ACTIVE_STATES.items():
        table = Table(table_name, MetaData(), autoload_with=src)
        active = select(table.c.status).where(table.c.status.in_(active_states)).limit(1)
        if src.execute(active).first():
            raise ValueError(f"Active execution must be resolved first: {table_name}")
    if dst.execute(text("SELECT version_num FROM alembic_version")).scalars().all() != [
        "20261103_0001"
    ]:
        raise ValueError("Target does not have the expected baseline revision")
    context = MigrationContext.configure(
        dst, opts={"compare_type": True, "compare_server_default": False}
    )
    structural_changes = [
        change
        for change in compare_metadata(context, Base.metadata)
        if (change[0][0] if isinstance(change, list) else change[0])
        not in {"modify_comment", "add_table_comment", "remove_table_comment"}
    ]
    if structural_changes:
        raise ValueError("Target schema does not match the current baseline")
    for name in sorted(new_names):
        count = dst.exec_driver_sql(f"SELECT COUNT(*) FROM `{name}`").scalar_one()
        if count != (1 if name == "auth_runtime" else 0):
            raise ValueError(f"Target is not empty: {name}")
    bootstrap = dst.exec_driver_sql(
        "SELECT id, mode, fingerprint, generation, ldap_config, changed_at, "
        "reconcile_owner, reconcile_until FROM auth_runtime"
    ).one()
    if tuple(bootstrap) != (1, "local", "", 0, None, None, "", None):
        raise ValueError("Target authentication singleton is not the baseline record")
    old_collations, new_collations = column_collations(src), column_collations(dst)
    old_meta, new_meta = MetaData(), MetaData()
    result = {}
    for name in sorted(new_names - NEW_TABLES):
        old = Table(name, old_meta, autoload_with=src)
        new = Table(name, new_meta, autoload_with=dst)
        extra = set(old.c.keys()) - set(new.c.keys())
        if set(new.c.keys()) - set(old.c.keys()) or extra != (
            OLD_COLUMNS if name == "ai_generation_stages" else set()
        ):
            raise ValueError(f"Unexpected columns in {name}")
        columns = list(new.c.keys())
        keys = [column.name for column in new.primary_key.columns]
        if not keys or any(key not in old.c for key in keys):
            raise ValueError(f"Missing primary key in {name}")
        for col in columns:
            old_type = re.sub(r' COLLATE "[^"]+"', "", str(old.c[col].type))
            new_type = re.sub(r' COLLATE "[^"]+"', "", str(new.c[col].type))
            if (
                old_type != new_type
                or old.c[col].nullable != new.c[col].nullable
                or old_collations[(name, col)] != new_collations[(name, col)]
            ):
                raise ValueError(f"Column type or nullability differs in {name}")
        result[name] = (old, new, columns, keys)
    return result


def validate_foreign_keys(dst: Connection, names: set[str]) -> None:
    metadata = MetaData()
    for name in sorted(names):
        table = Table(name, metadata, autoload_with=dst, extend_existing=True)
        for fk in table.foreign_key_constraints:
            parent = fk.referred_table.alias("fk_parent")
            pairs = [(item.parent, parent.c[item.column.name]) for item in fk.elements]
            join = and_(*(child == reference for child, reference in pairs))
            present = and_(*(child.is_not(None) for child, _ in pairs))
            absent = parent.c[next(iter(parent.primary_key)).name].is_(None)
            query = (
                select(next(iter(table.primary_key.columns)))
                .select_from(table.outerjoin(parent, join))
                .where(present, absent)
                .limit(1)
            )
            if dst.execute(query).first() is not None:
                raise ValueError(f"Foreign-key check failed: {name}")


def advance_auto_increments(src: Connection, dst: Connection, names: set[str]) -> None:
    query = text(
        "SELECT TABLE_NAME, AUTO_INCREMENT FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND AUTO_INCREMENT IS NOT NULL"
    )
    old = dict(src.execute(query).all())
    new = dict(dst.execute(query).all())
    if names & old.keys() != names & new.keys():
        raise ValueError("Source and target auto-increment columns differ")
    quote = dst.dialect.identifier_preparer.quote
    for name in sorted(names & old.keys() & new.keys()):
        if new[name] < old[name]:
            value = int(old[name])
            if value < 1:
                raise ValueError(f"Invalid auto-increment value: {name}")
            dst.exec_driver_sql(f"ALTER TABLE {quote(name)} AUTO_INCREMENT = {value}")
    current = dict(dst.execute(query).all())
    if any(current[name] < old[name] for name in names & old.keys() & current.keys()):
        raise ValueError("Target auto-increment validation failed")


def copy_database(source: Engine, target: Engine) -> tuple[int, int]:
    with source.connect() as src, target.connect() as dst:
        if (
            src.exec_driver_sql("SELECT @@server_uuid, DATABASE()").one()
            == dst.exec_driver_sql("SELECT @@server_uuid, DATABASE()").one()
        ):
            raise ValueError("Source and target are the same database")
        snapshot(src)
        tables = prepare(src, dst)
        source_hashes = {}
        total = 0
        try:
            dst.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
            dst.execute(text("DELETE FROM auth_runtime"))
            for name, (old, new, columns, keys) in tables.items():
                old_hash, expected_hash = hashlib.sha256(), hashlib.sha256()
                count = 0
                for batch in rows(src, old, columns, keys).partitions(500):
                    prepared = []
                    for value in batch:
                        original = dict(value)
                        feed(old_hash, original)
                        record = dict(original)
                        if name in TARGETS:
                            record["effective_import_id"] = None
                        feed(expected_hash, record)
                        prepared.append(record)
                    dst.execute(new.insert(), prepared)
                    count += len(prepared)
                actual_hash, actual_count = hashlib.sha256(), 0
                for value in rows(dst, new, columns, keys):
                    feed(actual_hash, dict(value))
                    actual_count += 1
                if count != actual_count or expected_hash.digest() != actual_hash.digest():
                    raise ValueError(f"Target contents differ: {name}")
                source_hashes[name] = (count, old_hash.digest())
                total += count
            dst.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            validate_foreign_keys(dst, set(Base.metadata.tables))
            with source.connect() as check:
                snapshot(check)
                for name, (old, _, columns, keys) in tables.items():
                    digest, count = hashlib.sha256(), 0
                    for value in rows(check, old, columns, keys):
                        feed(digest, dict(value))
                        count += 1
                    if (count, digest.digest()) != source_hashes[name]:
                        raise ValueError(f"Source changed during copy: {name}")
            dst.commit()
        except BaseException:
            dst.rollback()
            dst.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
            raise
        try:
            # MySQL ALTER TABLE commits implicitly, so run only after data commit.
            # A failure leaves the isolated target populated and must stop cutover.
            advance_auto_increments(src, dst, set(tables))
        except Exception as exc:
            raise RuntimeError("Target populated but auto-increment adjustment failed") from exc
        return len(tables), total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--target-config", type=Path, required=True)
    parser.add_argument("--verified-backup", type=Path, required=True)
    parser.add_argument("--writers-stopped", action="store_true")
    args = parser.parse_args()
    if (
        not args.writers_stopped
        or not args.verified_backup.is_file()
        or not args.verified_backup.stat().st_size
    ):
        parser.error("Stopped writers and a nonempty verified backup are required")
    try:
        tables, count = copy_database(
            make_engine(args.source_config), make_engine(args.target_config)
        )
    except Exception as exc:
        # Driver exceptions may contain SQL parameters or passwords.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Copy stopped: {message}", file=sys.stderr)
        return 1
    print(f"Copied and verified {count} rows across {tables} tables; target not switched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

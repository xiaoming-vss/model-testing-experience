"""Portable MySQL table snapshots; no credentials are written into the bundle."""

from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import pymysql
from sqlalchemy.engine import make_url


def connect(url: str):
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql"):
        raise ValueError("Snapshot requires a MySQL database")
    return pymysql.connect(
        host=parsed.host or "localhost",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password or "",
        database=parsed.database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )


def identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def encode(value):
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (datetime, date, time, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported snapshot type {type(value).__name__}")


def decode(value):
    if set(value) == {"$bytes"}:
        return base64.b64decode(value["$bytes"], validate=True)
    return value


def tables(connection):
    with connection.cursor() as cursor:
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        return [row[0] for row in cursor.fetchall()]


@contextmanager
def locked_tables(connection):
    """Block writes to this application's tables while DB and objects are copied."""
    names = tables(connection)
    if not names:
        raise ValueError("Source database has no tables")
    with connection.cursor() as cursor:
        cursor.execute("LOCK TABLES " + ", ".join(identifier(name) + " READ" for name in names))
    try:
        yield names
    finally:
        with connection.cursor() as cursor:
            cursor.execute("UNLOCK TABLES")


def dump_table(connection, name: str, destination: Path) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SHOW CREATE TABLE " + identifier(name))
        create = cursor.fetchone()[1]
    with (
        connection.cursor(pymysql.cursors.SSCursor) as cursor,
        destination.open("w", encoding="utf-8") as stream,
    ):
        cursor.execute("SELECT * FROM " + identifier(name))
        columns = [column[0] for column in cursor.description]
        stream.write(json.dumps({"table": name, "create": create, "columns": columns}) + "\n")
        count = 0
        while rows := cursor.fetchmany(500):
            for row in rows:
                stream.write(json.dumps(row, default=encode, ensure_ascii=False) + "\n")
                count += 1
    destination.chmod(0o600)
    return count


def restore_table(connection, source: Path, expected_name: str) -> int:
    with source.open(encoding="utf-8") as stream, connection.cursor() as cursor:
        metadata = json.loads(next(stream))
        if metadata["table"] != expected_name:
            raise ValueError("Database snapshot table mismatch")
        cursor.execute(metadata["create"])
        columns = ", ".join(identifier(column) for column in metadata["columns"])
        parameters = ", ".join(["%s"] * len(metadata["columns"]))
        insert = f"INSERT INTO {identifier(expected_name)} ({columns}) VALUES ({parameters})"
        count, batch = 0, []
        for line in stream:
            batch.append(json.loads(line, object_hook=decode))
            count += 1
            if len(batch) == 500:
                cursor.executemany(insert, batch)
                batch = []
        if batch:
            cursor.executemany(insert, batch)
        return count

"""Coordinated database/object bundles, restored only into isolated empty targets."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url

from testing_agent.core.object_storage import ObjectStorage
from testing_agent.services.database_snapshot import (
    connect,
    dump_table,
    locked_tables,
    restore_table,
    tables,
)
from testing_agent.services.integration_runtime import key_digest


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256")
    return digest.hexdigest()


def bundle_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Invalid or missing bundle file")
    return path


def verify_bundle(root: Path):
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("format") != 1:
        raise ValueError("Unsupported backup format")
    for item in manifest["tables"] + manifest["objects"]:
        path = bundle_path(root, item["path"])
        if checksum(path) != item["sha256"]:
            raise ValueError("Backup checksum mismatch")
    objects = {item["key"]: item for item in manifest["objects"]}
    if len(objects) != len(manifest["objects"]):
        raise ValueError("Duplicate backup object")
    for item in manifest["objects"]:
        if bundle_path(root, item["path"]).stat().st_size != item["size"]:
            raise ValueError("Backup object size mismatch")
    for row in manifest["files"]:
        item = objects.get(row["object_key"])
        if (
            item is None
            or row["bucket"] != manifest["bucket"]
            or row["size"] != item["size"]
            or row["sha256"] != item["sha256"]
        ):
            raise ValueError("Backup file reference mismatch")
    return manifest


def create_backup(settings, destination: Path):
    if not settings.s3.enabled:
        raise ValueError("S3 must be enabled")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    (destination / "tables").mkdir(mode=0o700)
    (destination / "objects").mkdir(mode=0o700)
    storage = ObjectStorage(settings.s3)
    database = connect(settings.database_url)
    manifest = {
        "format": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "bucket": settings.s3.bucket,
        "database": make_url(settings.database_url).database,
        "tables": [],
        "objects": [],
        "files": [],
        "integrationExecution": {
            "runtimeGeneration": settings.integration_execution.runtime_generation,
            "workerKeyFingerprint": key_digest(settings.integration_worker_key),
        },
    }
    try:
        with locked_tables(database) as names:
            for index, name in enumerate(names):
                path = destination / "tables" / f"{index}.jsonl"
                count = dump_table(database, name, path)
                manifest["tables"].append(
                    {
                        "name": name,
                        "path": str(path.relative_to(destination)),
                        "rows": count,
                        "sha256": checksum(path),
                    }
                )
            with database.cursor(pymysql_dict_cursor()) as cursor:
                cursor.execute(
                    "SELECT file_id, bucket, object_key, size, sha256 FROM stored_files "
                    "WHERE status IN ('attached', 'archived', 'ready')"
                )
                manifest["files"] = cursor.fetchall()
            keys: set[str] = set()
            prefix = settings.s3.prefix.strip("/")
            for page in storage.client.get_paginator("list_objects_v2").paginate(
                Bucket=settings.s3.bucket,
                Prefix=prefix + "/" if prefix else "",
            ):
                keys.update(item["Key"] for item in page.get("Contents", []))
            references: dict[str, list[dict[str, Any]]] = {}
            for row in manifest["files"]:
                if row["bucket"] != settings.s3.bucket:
                    raise ValueError("Referenced file uses a different bucket")
                keys.add(row["object_key"])
                references.setdefault(row["object_key"], []).append(row)
            for key in sorted(keys):
                obj = storage.client.get_object(Bucket=settings.s3.bucket, Key=key)
                path = destination / "objects" / (hashlib.sha256(key.encode()).hexdigest() + ".bin")
                try:
                    with path.open("wb") as stream:
                        for chunk in obj["Body"].iter_chunks(1024 * 1024):
                            stream.write(chunk)
                finally:
                    obj["Body"].close()
                path.chmod(0o600)
                digest, size = checksum(path), path.stat().st_size
                for row in references.get(key, []):
                    if row["size"] != size or row["sha256"] != digest:
                        raise ValueError("Referenced object differs from database; backup aborted")
                metadata = {
                    field: obj.get(field)
                    for field in (
                        "ContentType",
                        "ContentDisposition",
                        "CacheControl",
                        "ContentEncoding",
                        "Metadata",
                    )
                    if field in obj
                }
                manifest["objects"].append(
                    {
                        "key": key,
                        "path": str(path.relative_to(destination)),
                        "size": size,
                        "sha256": digest,
                        "metadata": metadata,
                    }
                )
    finally:
        database.close()
    # Only completed, fully verified bundles get a manifest and can be restored.
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (destination / "manifest.json").chmod(0o600)
    verify_bundle(destination)
    return {
        "tables": len(manifest["tables"]),
        "objects": len(manifest["objects"]),
        "referencedFiles": len(manifest["files"]),
    }


def pymysql_dict_cursor():
    from pymysql.cursors import DictCursor

    return DictCursor


def restore_backup(settings, source: Path):
    manifest = verify_bundle(source)
    integration_tables = {item["name"] for item in manifest["tables"]}
    if "integration_jobs" in integration_tables:
        validate_restore_execution(settings, manifest)
        if "integration_runtime" not in integration_tables:
            raise ValueError(
                "Restore requires code and backup with integration maintenance migration"
            )
    if not settings.s3.enabled or settings.s3.bucket == manifest["bucket"]:
        raise ValueError("Restore requires enabled S3 and a different empty bucket")
    if make_url(settings.database_url).database == manifest["database"]:
        raise ValueError("Restore requires a different empty database")
    storage = ObjectStorage(settings.s3)
    if storage.client.list_objects_v2(Bucket=settings.s3.bucket, MaxKeys=1).get("KeyCount", 0):
        raise ValueError("Restore bucket must be empty")
    database = connect(settings.database_url)
    try:
        if tables(database):
            raise ValueError("Restore database must be empty")
        for item in manifest["objects"]:
            with bundle_path(source, item["path"]).open("rb") as stream:
                storage.client.put_object(
                    Bucket=settings.s3.bucket, Key=item["key"], Body=stream, **item["metadata"]
                )
            obj = storage.client.get_object(Bucket=settings.s3.bucket, Key=item["key"])
            try:
                restored_hash = hashlib.sha256()
                for chunk in obj["Body"].iter_chunks(1024 * 1024):
                    restored_hash.update(chunk)
                digest = restored_hash.hexdigest()
            finally:
                obj["Body"].close()
            if digest != item["sha256"] or obj["ContentLength"] != item["size"]:
                raise ValueError("Restored object checksum mismatch")
        with database.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            for item in manifest["tables"]:
                count = restore_table(database, bundle_path(source, item["path"]), item["name"])
                if count != item["rows"]:
                    raise ValueError("Restored table row count mismatch")
            cursor.execute(
                "UPDATE stored_files SET bucket=%s WHERE bucket=%s",
                (settings.s3.bucket, manifest["bucket"]),
            )
            if "file_verifications" in integration_tables:
                # Restore into a distinct bucket cannot resume a source writer's permit.
                # Retain unknown-write tombstones conservatively for repeated cleanup.
                cursor.execute(
                    "UPDATE file_verifications SET bucket=%s, "
                    "gc_after=CASE WHEN state='published' THEN gc_after ELSE UTC_TIMESTAMP() END, "
                    "state=CASE WHEN state='running' THEN 'abandoned' ELSE state END "
                    "WHERE bucket=%s",
                    (settings.s3.bucket, manifest["bucket"]),
                )
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        if "integration_jobs" in integration_tables:
            quarantine_restored_integrations(database, settings)
        return {
            "tables": len(manifest["tables"]),
            "objects": len(manifest["objects"]),
            "referencedFiles": len(manifest["files"]),
        }
    finally:
        database.close()


def validate_restore_execution(settings, manifest):
    execution = settings.integration_execution
    original = manifest.get("integrationExecution", {})
    if execution.enabled or execution.accept_submissions or execution.claim_enabled:
        raise ValueError("Restore requires disabled integration execution, submissions and claims")
    if (
        not settings.integration_worker_key
        or not execution.runtime_generation
        or execution.runtime_generation == original.get("runtimeGeneration")
        or key_digest(settings.integration_worker_key) == original.get("workerKeyFingerprint")
        or not original.get("workerKeyFingerprint")
    ):
        raise ValueError("Restore requires a new dedicated Worker key and runtime generation")


def quarantine_restored_integrations(database, settings):
    """Maintenance-only, after restore verification. Remote effects cannot be rolled back."""
    database.begin()
    try:
        with database.cursor() as cursor:
            cursor.execute(
                "UPDATE integration_jobs SET recovery_required=1, status='quarantined', "
                "active_scope=NULL, active_target=NULL, lease_expires_at=NULL "
                "WHERE status IN ('queued','claimed','running','unknown','quarantined') "
                "OR recovery_required=1 OR job_id IN "
                "(SELECT job_id FROM integration_job_steps "
                "WHERE status IN ('write_intent','unknown'))"
            )
            now = datetime.now(UTC).replace(tzinfo=None)
            cursor.execute(
                "INSERT INTO integration_runtime "
                "(id,restore_id,runtime_generation,worker_key_digest,blocked,"
                "created_at,updated_at) "
                "VALUES (1,%s,%s,%s,1,%s,%s) ON DUPLICATE KEY UPDATE "
                "restore_id=VALUES(restore_id), runtime_generation=VALUES(runtime_generation), "
                "worker_key_digest=VALUES(worker_key_digest), blocked=1, "
                "updated_at=VALUES(updated_at)",
                (
                    uuid4().hex,
                    settings.integration_execution.runtime_generation,
                    key_digest(settings.integration_worker_key),
                    now,
                    now,
                ),
            )
        database.commit()
    except Exception:
        database.rollback()
        raise

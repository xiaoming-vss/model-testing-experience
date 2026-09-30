"""Readable skill object paths; temporary upload IDs stay outside the published tree."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.project import Project
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.stored_file import utcnow


def skill_key(prefix, skill, path):
    scope = "system" if skill.is_default else "projects/" + skill.project_id
    key = "/".join(filter(None, [prefix.strip("/"), "skills", scope, skill.filename, path]))
    if len(key) > 512 or len(key.encode()) > 1024:
        raise AppError(400, "技能文件完整存储路径过长", 400)
    return key


def retire_copy(files, row, key):
    files.session.add(
        StoredFile(
            file_id=new_id(),
            project_id=row.project_id,
            uploaded_by=row.uploaded_by,
            filename=row.filename,
            content_type=row.content_type,
            size=row.size,
            sha256=row.sha256,
            bucket=row.bucket,
            object_key=key,
            staging_key="",
            status="deleting",
            purpose="project_skill",
            resource_type="project_skill",
            resource_id=row.resource_id,
            expires_at=utcnow() + timedelta(seconds=files.settings.signature_seconds),
        )
    )


@asynccontextmanager
async def publish_skill_files(files, skill, manifest):
    """Caller holds the scope lock and commits inside this context.

    Keep temporary S3 backups for compensation if a copy or database commit fails.
    These are upload cleanup objects, not user-visible skill versions.
    """
    moves = []
    for entry in manifest:
        row = await files.get(entry["fileId"])
        target = skill_key(files.settings.prefix, skill, entry["path"])
        if row.object_key != target:
            moves.append((row, row.object_key, target))
    completed, backups = [], []
    client = files.storage.client

    async def copy(bucket, source, target):
        await asyncio.to_thread(
            client.copy_object,
            Bucket=bucket,
            Key=target,
            CopySource={"Bucket": bucket, "Key": source},
        )

    try:
        for row, source, target in moves:
            backup = None
            try:
                await asyncio.to_thread(client.head_object, Bucket=row.bucket, Key=target)
            except client.exceptions.ClientError as exc:
                if exc.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
                    raise
            else:
                backup = "/".join(
                    filter(
                        None, [files.settings.prefix.strip("/"), "_temporary", "skills", new_id()]
                    )
                )
                await copy(row.bucket, target, backup)
                backups.append((row.bucket, backup))
                retire_copy(files, row, backup)
            completed.append((row.bucket, target, backup))
            await copy(row.bucket, source, target)
            retire_copy(files, row, source)
            row.object_key = target
        yield
    except Exception:
        for bucket, target, backup in reversed(completed):
            if backup:
                await copy(bucket, backup, target)
            else:
                await asyncio.to_thread(client.delete_object, Bucket=bucket, Key=target)
        for bucket, backup in backups:
            await asyncio.to_thread(client.delete_object, Bucket=bucket, Key=backup)
        await files.session.rollback()
        raise


async def migrate_skill_paths(files):
    identifiers = list(await files.session.scalars(select(ProjectSkillSpace.skill_space_id)))
    results = []
    for identifier in identifiers:
        skill = await files.session.scalar(
            select(ProjectSkillSpace).where(ProjectSkillSpace.skill_space_id == identifier)
        )
        if skill.project_id:
            await files.session.scalar(
                select(Project).where(Project.project_id == skill.project_id).with_for_update()
            )
        await files.session.refresh(skill, with_for_update=True)
        async with publish_skill_files(files, skill, skill.manifest):
            await files.session.commit()
        results.append({"name": skill.filename, "files": len(skill.manifest)})
    return results

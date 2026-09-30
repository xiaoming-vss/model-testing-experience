"""Publish trusted on-disk default skills through the shared S3 file lifecycle."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.core.sid import new_id
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.project_skill_space import replace_manifest
from testing_agent.services.skill_storage import publish_skill_files
from testing_agent.services.stored_file import utcnow


def inspect_folder(folder: Path, maximum: int):
    entries = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"技能目录不接受符号链接: {path}")
        if path.is_file():
            entries.append((path.relative_to(folder).as_posix(), path.read_bytes()))
    ProjectSkillUploadRequest(
        name=folder.name,
        files=[{"path": name, "fileId": str(i)} for i, (name, _) in enumerate(entries)],
    )
    if sum(len(data) for _, data in entries) > maximum:
        raise ValueError(f"技能文件夹超过大小限制: {folder.name}")
    return entries


async def sync_builtin_skills(files, source: Path):
    if not source.is_dir():
        raise ValueError("默认技能源目录不存在")
    # Validate the whole source before publishing any skill.
    folders = [p for p in sorted(source.iterdir()) if p.is_dir()]
    if not folders or any(p.is_symlink() for p in folders):
        raise ValueError("默认技能源目录为空或包含目录链接")
    content = [
        (folder.name, inspect_folder(folder, files.settings.max_bytes)) for folder in folders
    ]
    session = files.session
    names = [name for name, _ in content]
    collision = await session.scalar(
        select(ProjectSkillSpace).where(
            ProjectSkillSpace.is_default.is_(False), ProjectSkillSpace.filename.in_(names)
        )
    )
    if collision:
        raise AppError(409, f"项目自定义技能已占用默认技能名称: {collision.filename}", 409)
    results = []
    for name, entries in content:
        skill = await session.scalar(
            select(ProjectSkillSpace).where(
                ProjectSkillSpace.scope_key == "system", ProjectSkillSpace.filename == name
            )
        )
        if skill is None:
            skill = ProjectSkillSpace(
                skill_space_id=new_id(),
                project_id=None,
                scope_key="system",
                filename=name,
                is_default=True,
                manifest=[],
                hash="",
                size_bytes=0,
            )
        skill_id = skill.skill_space_id
        manifest = []
        for path, data in entries:
            file_id = new_id()
            key = "/".join(
                filter(
                    None,
                    [
                        files.settings.prefix.strip("/"),
                        "_temporary",
                        "skills",
                        "system",
                        file_id,
                        path.rsplit("/", 1)[-1],
                    ],
                )
            )
            row = StoredFile(
                file_id=file_id,
                project_id="",
                uploaded_by="system",
                filename=path.rsplit("/", 1)[-1],
                content_type="application/octet-stream",
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                bucket=files.settings.bucket,
                object_key=key,
                staging_key="",
                status="pending",
                purpose="project_skill",
                resource_type="project_skill",
                resource_id=skill_id,
                expires_at=utcnow() + timedelta(hours=files.settings.temporary_hours),
            )
            session.add(row)
            await session.commit()  # Failed uploads remain eligible for shared cleanup.
            await asyncio.to_thread(
                files.storage.client.put_object,
                Bucket=row.bucket,
                Key=key,
                Body=data,
                ContentType=row.content_type,
            )
            row.status, row.completed_at = "ready", utcnow()
            await session.commit()
            manifest.append(
                {"path": path, "fileId": file_id, "size": row.size, "sha256": row.sha256}
            )
        session.add(skill)
        # Lock an existing catalog entry so concurrent syncs retire the actual prior content.
        await session.flush()
        await session.refresh(skill, with_for_update=True)
        for entry in manifest:
            row = await files.get(entry["fileId"], lock=True)
            row.status = "attached"
        async with publish_skill_files(files, skill, manifest):
            await replace_manifest(session, skill, manifest, files.settings.signature_seconds)
            await session.commit()
        results.append({"name": name, "files": len(manifest)})
    return results

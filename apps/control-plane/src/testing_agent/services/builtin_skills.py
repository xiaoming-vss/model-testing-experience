"""Publish trusted on-disk default skills through the shared S3 file lifecycle."""

import hashlib
from pathlib import Path

from sqlalchemy import select

from testing_agent.core.errors import AppError
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest, SkillFileInput
from testing_agent.services.skill_storage import SkillPublisher
from testing_agent.services.stored_file import StoredFileService


def _content_signature(entries: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for path, data in sorted(entries):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def _manifest_signature(skill: ProjectSkillSpace) -> str:
    digest = hashlib.sha256()
    for entry in sorted(skill.manifest or [], key=lambda item: item["path"]):
        digest.update(entry["path"].encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(entry.get("sha256", "")))
    return digest.hexdigest()


def inspect_folder(folder: Path, maximum: int) -> list[tuple[str, bytes]]:
    entries = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"技能目录不接受符号链接: {path}")
        if path.is_file():
            entries.append((path.relative_to(folder).as_posix(), path.read_bytes()))
    ProjectSkillUploadRequest(
        name=folder.name,
        files=[SkillFileInput(path=name, file_id=str(i)) for i, (name, _) in enumerate(entries)],
    )
    if sum(len(data) for _, data in entries) > maximum:
        raise ValueError(f"技能文件夹超过大小限制: {folder.name}")
    return entries


async def sync_builtin_skills(files: StoredFileService, source: Path) -> list[dict[str, str | int]]:
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
    await session.commit()
    existing = {
        row.filename: row
        for row in (
            await session.scalars(
                select(ProjectSkillSpace).where(
                    ProjectSkillSpace.is_default.is_(True),
                    ProjectSkillSpace.filename.in_(names),
                )
            )
        ).all()
    }
    results: list[dict[str, str | int]] = []
    publisher = SkillPublisher(files)
    for name, entries in content:
        current = existing.get(name)
        if current is not None and _manifest_signature(current) == _content_signature(entries):
            results.append({"name": name, "files": len(entries)})
            continue
        await publisher.builtin(name, entries)
        results.append({"name": name, "files": len(entries)})
    return results

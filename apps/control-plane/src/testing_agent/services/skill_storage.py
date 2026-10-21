"""Publish immutable skill batches with durable copy permits and short transactions."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import AppError, ErrForbidden, ErrNotFound
from testing_agent.core.sid import new_id
from testing_agent.models.file_verification import FileVerification
from testing_agent.models.project_skill_space import ProjectSkillSpace
from testing_agent.models.stored_file import StoredFile
from testing_agent.repositories.skill_publication import SkillPublicationRepository
from testing_agent.schemas.project_skill_space import ProjectSkillUploadRequest
from testing_agent.services.file_verification import VERIFY_WINDOW, FileVerificationWorkflow
from testing_agent.services.stored_file import StoredFileService, utcnow


@dataclass(frozen=True)
class SkillTarget:
    skill_id: str
    project_id: str
    name: str
    expected_hash: str | None

    @property
    def scope(self) -> str:
        return self.project_id or "system"


def skill_key(prefix: str, target: SkillTarget, batch: str, path: str) -> str:
    scope = "projects/" + target.project_id if target.project_id else "system"
    key = "/".join(filter(None, [prefix.strip("/"), "skills", scope, target.name, batch, path]))
    if len(key) > 512 or len(key.encode()) > 1024:
        raise AppError(400, "技能文件完整存储路径过长", 400)
    return key


@dataclass(frozen=True)
class SkillCopy:
    file_id: str
    operation_id: str
    path: str
    source_key: str
    target_key: str
    size: int
    sha256: str
    data: bytes | None = None

    def entry(self) -> dict[str, Any]:
        return {"path": self.path, "fileId": self.file_id, "size": self.size, "sha256": self.sha256}


def retire_copy(files: StoredFileService, row: StoredFile, key: str) -> None:
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


async def replace_manifest(
    session: AsyncSession,
    skill: ProjectSkillSpace,
    manifest: list[dict[str, Any]],
    signature_seconds: int,
) -> None:
    """Caller owns the atomic publication/deletion transaction; no storage calls."""
    keep = {entry["fileId"] for entry in manifest}
    old = {entry["fileId"] for entry in (skill.manifest or [])} - keep
    rows = await SkillPublicationRepository(session).files(sorted(old)) if old else {}
    for row in rows.values():
        if row.resource_type == "project_skill" and row.resource_id == skill.skill_space_id:
            row.status = "deleting"
            row.expires_at = utcnow() + timedelta(seconds=signature_seconds)
    skill.manifest = sorted(manifest, key=lambda entry: entry["path"])
    skill.hash = hashlib.sha256(json.dumps(skill.manifest, sort_keys=True).encode()).hexdigest()
    skill.size_bytes = sum(entry["size"] for entry in manifest)
    skill.updated_at = utcnow()


class SkillPublisher:
    """Owns reservation/publication commits; project and CLI entry points share one protocol."""

    def __init__(self, files: StoredFileService) -> None:
        self.files, self.session = files, files.session
        self.repository = SkillPublicationRepository(self.session)

    async def scope(self, project_id: str, actor: str | None) -> None:
        if project_id:
            if actor is not None:
                await FileVerificationWorkflow(
                    self.session, self.files.settings, self.files.storage
                ).authorized(project_id, actor, action="manage")
            elif await self.repository.scope(project_id) is None:
                raise ErrNotFound()

    async def catalog(self, project_id: str, name: str) -> ProjectSkillSpace | None:
        rows = await self.repository.catalog(name)
        if project_id and any(row.is_default for row in rows):
            raise AppError(409, "不能上传与系统默认 Skill 同名的技能", 409)
        if not project_id and any(not row.is_default for row in rows):
            raise AppError(409, "项目自定义技能已占用默认技能名称", 409)
        return next((row for row in rows if row.scope_key == (project_id or "system")), None)

    def target(self, project_id: str, name: str, skill: ProjectSkillSpace | None) -> SkillTarget:
        return SkillTarget(
            skill.skill_space_id if skill is not None else new_id(),
            project_id,
            skill.filename if skill is not None else name,
            skill.hash if skill is not None else None,
        )

    def validate_file(self, row: StoredFile, target: SkillTarget, actor: str | None) -> None:
        if row.project_id != target.project_id or row.purpose != "project_skill":
            raise ErrForbidden()
        if row.bucket != self.files.settings.bucket:
            raise AppError(503, "文件存储配置与记录不一致", 503)
        if row.status == "attached" and (row.resource_type, row.resource_id) == (
            "project_skill",
            target.skill_id,
        ):
            return
        if actor is None or row.uploaded_by != actor:
            raise ErrForbidden()
        if row.status != "ready" or row.expires_at <= utcnow():
            raise AppError(409, "文件未完成上传或不可关联", 409)

    def reserve(
        self,
        target: SkillTarget,
        row: StoredFile,
        path: str,
        batch: str,
        *,
        data: bytes | None = None,
    ) -> SkillCopy:
        operation_id = new_id()
        key = skill_key(self.files.settings.prefix, target, batch, path)
        now = utcnow()
        self.session.add(
            FileVerification(
                operation_id=operation_id,
                file_id=row.file_id,
                bucket=row.bucket,
                object_key=key,
                state="running",
                deadline=now + VERIFY_WINDOW,
                gc_after=now + VERIFY_WINDOW,
            )
        )
        if data is not None:
            row.object_key = key
            row.verification_id = operation_id
        return SkillCopy(
            row.file_id, operation_id, path, row.object_key, key, row.size, row.sha256, data
        )

    async def project(
        self, project_id: str, body: ProjectSkillUploadRequest, actor: str
    ) -> ProjectSkillSpace:
        try:
            await self.scope(project_id, actor)
            skill = await self.catalog(project_id, body.name)
            target = self.target(project_id, body.name, skill)
            old_paths = (
                {entry["fileId"]: entry["path"] for entry in skill.manifest} if skill else {}
            )
            rows = await self.repository.files([entry.file_id for entry in body.files])
            batch, copies = new_id(), []
            for entry in body.files:
                row = rows.get(entry.file_id)
                if row is None:
                    raise ErrNotFound()
                self.validate_file(row, target, actor)
                if entry.file_id in old_paths and old_paths[entry.file_id] != entry.path:
                    raise AppError(400, "更改技能文件路径需要重新上传文件", 400)
                if row.filename != entry.path.rsplit("/", 1)[-1]:
                    raise AppError(400, "技能文件名与上传文件不一致", 400)
                copies.append(self.reserve(target, row, entry.path, batch))
            if sum(item.size for item in copies) > self.files.settings.max_bytes:
                raise AppError(400, "技能文件夹超过大小限制", 400)
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return await self.finish(target, copies, actor)

    async def builtin(self, name: str, entries: list[tuple[str, bytes]]) -> ProjectSkillSpace:
        try:
            skill = await self.catalog("", name)
            target = self.target("", name, skill)
            batch, copies = new_id(), []
            for path, data in entries:
                row = StoredFile(
                    file_id=new_id(),
                    project_id="",
                    uploaded_by="system",
                    filename=path.rsplit("/", 1)[-1],
                    content_type="application/octet-stream",
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    bucket=self.files.settings.bucket,
                    object_key="",
                    staging_key="",
                    status="pending",
                    purpose="project_skill",
                    resource_type="project_skill",
                    resource_id=target.skill_id,
                    expires_at=utcnow() + timedelta(hours=self.files.settings.temporary_hours),
                )
                self.session.add(row)
                copies.append(self.reserve(target, row, path, batch, data=data))
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return await self.finish(target, copies, None)

    def transfer(self, copy: SkillCopy) -> None:
        storage = self.files.storage
        filename = copy.path.rsplit("/", 1)[-1]
        if copy.data is None:
            storage.seal(copy.source_key, copy.target_key, copy.size, copy.sha256, filename)
            return
        storage.client.put_object(
            Bucket=self.files.settings.bucket,
            Key=copy.target_key,
            Body=copy.data,
            ContentType="application/octet-stream",
        )
        # Trusted CLI bytes still require a verified storage receipt before publication.
        obj = storage.client.get_object(Bucket=self.files.settings.bucket, Key=copy.target_key)
        try:
            content = obj["Body"].read(copy.size + 1)
        finally:
            obj["Body"].close()
        if len(content) != copy.size or hashlib.sha256(content).hexdigest() != copy.sha256:
            raise AppError(409, "技能文件校验失败", 409)

    async def discard(self, copies: list[SkillCopy], *, uncertain: set[str] | None = None) -> None:
        rows = await self.repository.operations([copy.operation_id for copy in copies])
        for row in rows.values():
            if row.state != "published":
                unknown = row.operation_id in (uncertain or set())
                row.state = "abandoned" if unknown else "discarded"
                row.settled_at = None if unknown else utcnow()
                row.gc_after = utcnow()
        await self.session.commit()

    async def finish(
        self, target: SkillTarget, copies: list[SkillCopy], actor: str | None
    ) -> ProjectSkillSpace:
        try:
            for copy in copies:
                await asyncio.to_thread(self.transfer, copy)
        except asyncio.CancelledError:
            # The current storage thread may finish later. Keep all permits for bounded GC.
            raise
        except Exception as exc:
            await self.discard(
                copies, uncertain=set() if isinstance(exc, AppError) else {copy.operation_id}
            )
            raise
        try:
            await self.scope(target.project_id, actor)
            skill = await self.catalog(target.project_id, target.name)
            if target.expected_hash is None:
                if skill is not None:
                    raise AppError(409, "技能已更新，请刷新后重试", 409)
                skill = ProjectSkillSpace(
                    skill_space_id=target.skill_id,
                    project_id=target.project_id or None,
                    scope_key=target.scope,
                    filename=target.name,
                    is_default=not target.project_id,
                    manifest=[],
                    hash="",
                    size_bytes=0,
                )
                self.session.add(skill)
            elif (
                skill is None
                or skill.skill_space_id != target.skill_id
                or skill.hash != target.expected_hash
            ):
                raise AppError(409, "技能已更新，请刷新后重试", 409)
            rows = await self.repository.files([copy.file_id for copy in copies])
            operations = await self.repository.operations([copy.operation_id for copy in copies])
            for copy in copies:
                row, operation = rows.get(copy.file_id), operations.get(copy.operation_id)
                if (
                    row is None
                    or operation is None
                    or operation.state != "running"
                    or operation.deadline <= utcnow()
                    or row.object_key != copy.source_key
                    or row.size != copy.size
                    or row.sha256 != copy.sha256
                    or row.filename != copy.path.rsplit("/", 1)[-1]
                    or row.bucket != self.files.settings.bucket
                ):
                    raise AppError(409, "技能发布已失效，请刷新后重试", 409)
                if copy.data is None:
                    self.validate_file(row, target, actor)
                elif (
                    row.status != "pending"
                    or row.verification_id != copy.operation_id
                    or row.expires_at <= utcnow()
                ):
                    raise AppError(409, "技能上传已失效，请重试", 409)
                if row.object_key != copy.target_key:
                    retire_copy(self.files, row, row.object_key)
                row.object_key, row.status = copy.target_key, "attached"
                row.resource_type, row.resource_id = "project_skill", target.skill_id
                row.completed_at = row.completed_at or utcnow()
                operation.state, operation.settled_at = "published", utcnow()
            await replace_manifest(
                self.session,
                skill,
                [copy.entry() for copy in copies],
                self.files.settings.signature_seconds,
            )
            await self.session.commit()
            return skill
        except BaseException:
            await self.session.rollback()
            await self.discard(copies)
            raise

    async def migrate(self, identifier: str) -> bool:
        try:
            skill = await self.repository.skill(identifier)
            if skill is None:
                raise ErrNotFound()
            project_id, name = skill.project_id or "", skill.filename
            await self.scope(project_id, None)
            skill = await self.catalog(project_id, name)
            if skill is None or skill.skill_space_id != identifier:
                raise ErrNotFound()
            target = self.target(project_id, name, skill)
            rows = await self.repository.files([entry["fileId"] for entry in skill.manifest])
            if len(rows) != len(skill.manifest):
                raise ErrNotFound()
            if all(
                self.current_layout(target, rows[entry["fileId"]], entry["path"])
                for entry in skill.manifest
            ):
                await self.session.commit()
                return False
            copies, batch = [], new_id()
            for entry in skill.manifest:
                row = rows.get(entry["fileId"])
                if row is None:
                    raise ErrNotFound()
                self.validate_file(row, target, None)
                copies.append(self.reserve(target, row, entry["path"], batch))
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        await self.finish(target, copies, None)
        return True

    def current_layout(self, target: SkillTarget, row: StoredFile, path: str) -> bool:
        parent = row.object_key.removesuffix("/" + path)
        batch = parent.rsplit("/", 1)[-1]
        try:
            UUID(batch)
        except ValueError:
            return False
        return row.object_key == skill_key(self.files.settings.prefix, target, batch, path)


async def migrate_skill_paths(files: StoredFileService) -> list[dict[str, Any]]:
    publisher = SkillPublisher(files)
    identifiers = await publisher.repository.identifiers()
    await files.session.commit()
    results = []
    for identifier in identifiers:
        migrated = await publisher.migrate(identifier)
        skill = await publisher.repository.skill(identifier)
        if skill is not None:
            results.append(
                {"name": skill.filename, "files": len(skill.manifest), "migrated": migrated}
            )
        await files.session.commit()
    return results

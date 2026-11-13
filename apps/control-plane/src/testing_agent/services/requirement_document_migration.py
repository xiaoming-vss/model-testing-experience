"""Migrate legacy plain-text requirements to sanitized rich-text documents.

历史 TXT 需求只保留读取兼容，不再允许新建。迁移把正文转成清洗后的
requirement.html，并补齐统一文件记录，之后需求可以按 richtext 正常预览、
提取和重新生成。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.domain.rich_text import has_rich_text_content, sanitize_rich_text
from testing_agent.models.project import Project
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.schemas.stored_file import FileUploadRequest
from testing_agent.services.stored_file import StoredFileService

_PARAGRAPH_BREAK = re.compile(r"\n{2,}")


def plain_text_to_rich_html(text: str) -> str:
    """把纯文本转成白名单内的富文本 HTML；段落之间用 p，段内换行用 br。"""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    paragraphs = [part.strip() for part in _PARAGRAPH_BREAK.split(normalized) if part.strip()]
    body = "".join(f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)
    return sanitize_rich_text(body)


def _looks_like_artifact(content: str) -> bool:
    stripped = content.lstrip()
    return (
        stripped.startswith("{")
        and '"artifactType"' in content
        and ("readable_requirement_material" in content)
    )


def _rich_filename(requirement: Requirement) -> str:
    stem = Path(requirement.document_filename or "requirement.txt").stem.strip() or "requirement"
    return f"{stem[:240]}.html"


async def _context(session: AsyncSession, requirement: Requirement) -> tuple[str, str]:
    sprint = await session.scalar(select(Sprint).where(Sprint.sprint_id == requirement.sprint_id))
    if sprint is None:
        raise LookupError("需求所属迭代不存在")
    project = await session.scalar(select(Project).where(Project.project_id == sprint.project_id))
    if project is None:
        raise LookupError("需求所属项目不存在")
    return sprint.project_id, project.user_id


async def _convert(
    files: StoredFileService,
    requirement: Requirement,
    content: str,
    *,
    project_id: str,
    owner_id: str,
    filename: str,
) -> str:
    data = content.encode("utf-8")
    ticket = await files.initiate(
        owner_id,
        FileUploadRequest(
            project_id=project_id,
            filename=filename,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            purpose="requirement",
        ),
    )
    staged = await files.get(ticket["fileId"])
    await asyncio.to_thread(
        files.storage.client.put_object,
        Bucket=staged.bucket,
        Key=staged.staging_key,
        Body=data,
    )
    await files.complete(owner_id, staged.file_id)
    row = await files.get(staged.file_id)
    await files.attach(
        owner_id,
        row.file_id,
        project_id,
        "requirement",
        requirement.requirement_id,
        purpose="requirement",
    )
    requirement.document_type = "richtext"
    requirement.document_file_id = row.file_id
    requirement.document_filename = row.filename
    requirement.document_hash = row.sha256
    requirement.document_content = ""
    requirement.document_download_url = f"/v1/requirements/{requirement.requirement_id}/download"
    await files.session.commit()
    return row.file_id


async def migrate_text_requirements(
    files: StoredFileService, *, apply: bool = False
) -> list[dict[str, Any]]:
    """转换所有 document_type=text 的需求；默认只报告，不写库也不写对象存储。"""

    session = files.session
    requirement_ids = (
        await session.scalars(
            select(Requirement.requirement_id)
            .where(Requirement.document_type == "text")
            .order_by(Requirement.id)
        )
    ).all()
    results: list[dict[str, Any]] = []
    for requirement_id in requirement_ids:
        requirement = await session.scalar(
            select(Requirement).where(Requirement.requirement_id == requirement_id)
        )
        if requirement is None:
            continue
        result: dict[str, Any] = {
            "requirementId": requirement.requirement_id,
            "name": requirement.name,
        }
        content = plain_text_to_rich_html(requirement.document_content or "")
        original = requirement.document_content or ""
        if not original.strip():
            result["status"] = "skipped_empty"
            results.append(result)
            continue
        if _looks_like_artifact(original):
            result["status"] = "skipped_artifact"
            results.append(result)
            continue
        if not has_rich_text_content(content):
            result["status"] = "skipped_empty_html"
            results.append(result)
            continue
        filename = _rich_filename(requirement)
        result.update(
            {
                "status": "would_convert" if not apply else "converting",
                "filename": filename,
                "sourceBytes": len(original.encode("utf-8")),
                "htmlBytes": len(content.encode("utf-8")),
            }
        )
        if not apply:
            results.append(result)
            continue
        try:
            project_id, owner_id = await _context(session, requirement)
            file_id = await _convert(
                files,
                requirement,
                content,
                project_id=project_id,
                owner_id=owner_id,
                filename=filename,
            )
        except Exception as exc:
            await session.rollback()
            result["status"] = "failed"
            result["error"] = str(exc) or type(exc).__name__
        else:
            result["status"] = "converted"
            result["fileId"] = file_id
        results.append(result)
    return results

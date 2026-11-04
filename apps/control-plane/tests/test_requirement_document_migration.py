from sqlalchemy import func, select
from support.stored_files import files as files
from support.stored_files import longtext_sqlite as longtext_sqlite

from testing_agent.models.requirement import Requirement
from testing_agent.models.stored_file import StoredFile
from testing_agent.services.requirement_document_migration import (
    migrate_text_requirements,
    plain_text_to_rich_html,
)


def test_plain_text_to_rich_html_escapes_and_keeps_paragraphs():
    html = plain_text_to_rich_html("第一段 <script>alert(1)</script>\n换行\n\n第二段")

    assert "<p>第一段 &lt;script&gt;alert(1)&lt;/script&gt;<br>换行</p>" in html
    assert "<p>第二段</p>" in html
    assert "<script>" not in html


async def test_dry_run_reports_without_writing(files):
    requirement = await files.session.scalar(
        select(Requirement).where(Requirement.requirement_id == "r")
    )
    requirement.document_type = "text"
    requirement.document_content = "历史纯文本"
    requirement.document_filename = "requirement.txt"
    await files.session.commit()

    results = await migrate_text_requirements(files, apply=False)

    assert results == [
        {
            "requirementId": "r",
            "name": "existing",
            "status": "would_convert",
            "filename": "requirement.html",
            "sourceBytes": len("历史纯文本".encode()),
            "htmlBytes": len("<p>历史纯文本</p>".encode()),
        }
    ]
    await files.session.refresh(requirement)
    assert requirement.document_type == "text"
    assert requirement.document_content == "历史纯文本"


async def test_apply_converts_legacy_text_to_attached_rich_text(files):
    requirement = await files.session.scalar(
        select(Requirement).where(Requirement.requirement_id == "r")
    )
    requirement.document_type = "text"
    requirement.document_content = "第一段\n\n第二段"
    requirement.document_filename = "requirement.txt"
    await files.session.commit()

    results = await migrate_text_requirements(files, apply=True)

    assert results[0]["status"] == "converted"
    file_id = results[0]["fileId"]
    await files.session.refresh(requirement)
    assert requirement.document_type == "richtext"
    assert requirement.document_file_id == file_id
    assert requirement.document_filename == "requirement.html"
    assert requirement.document_content == ""
    assert requirement.document_download_url == "/v1/requirements/r/download"
    row = await files.get(file_id)
    assert row.status == "attached"
    assert row.purpose == "requirement"
    assert row.resource_type == "requirement"
    assert row.resource_id == "r"
    assert files.storage.read_text(row.object_key) == "<p>第一段</p><p>第二段</p>"


async def test_migration_is_idempotent(files):
    requirement = await files.session.scalar(
        select(Requirement).where(Requirement.requirement_id == "r")
    )
    requirement.document_type = "text"
    requirement.document_content = "历史纯文本"
    await files.session.commit()

    await migrate_text_requirements(files, apply=True)
    results = await migrate_text_requirements(files, apply=True)

    assert results == []
    count = await files.session.scalar(
        select(func.count()).select_from(StoredFile).where(StoredFile.purpose == "requirement")
    )
    assert count == 1

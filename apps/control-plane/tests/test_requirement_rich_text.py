"""HTML source round trips through sealed S3 files and project-scoped image links."""

import hashlib

import pytest
from test_stored_files import files as files
from test_stored_files import upload

from testing_agent.core.errors import AppError
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.schemas.requirement import CreateRequirementRequest, UpdateRequirementRequest
from testing_agent.services.project import ProjectService
from testing_agent.services.requirement import RequirementService
from testing_agent.services.sprint import SprintService


def service(files):
    return RequirementService(
        RequirementRepository(files.session),
        SprintService(
            SprintRepository(files.session), ProjectService(ProjectRepository(files.session))
        ),
        files=files,
    )


async def test_html_is_sanitized_before_ready_and_images_survive_reopen(files):
    image, _ = await upload(files, b"\x89PNG\r\n\x1a\nimage", "screen.png", "attachment")
    await files.complete("owner", image.file_id)
    raw = (
        '<h2 onclick="alert(1)">需求</h2><script>alert(1)</script>'
        f'<img data-file-id="{image.file_id}" src="https://expired.example/image">'
    )
    row, _ = await upload(files, raw.encode(), "requirement.html")
    await files.complete("owner", row.file_id)
    clean = files.storage.read_text(row.object_key)
    assert "script" not in clean and "onclick" not in clean and "src=" not in clean
    assert "<h2>需求</h2>" in clean
    assert row.sha256 == hashlib.sha256(clean.encode()).hexdigest()
    assert row.size == len(clean.encode())
    result = await service(files).create(
        "owner",
        "s",
        CreateRequirementRequest(
            name="Rich requirement", documentType="richtext", documentFileId=row.file_id
        ),
    )
    assert result["documentType"] == "richtext"
    assert result["documentContent"] == ""
    assert result["documentHash"] == row.sha256
    assert image.resource_id == result["requirementId"]
    assert (await files.download("viewer", image.file_id))["filename"] == "screen.png"
    # A different project member may edit a requirement while retaining its images.
    replacement, _ = await upload(
        files, clean.replace("需求", "更新需求").encode(), "requirement.html"
    )
    await files.complete("owner", replacement.file_id)
    replacement.uploaded_by = "member"
    await files.session.commit()
    updated = await service(files).update(
        "member",
        result["requirementId"],
        UpdateRequirementRequest(
            name="Updated", documentType="richtext", documentFileId=replacement.file_id
        ),
    )
    assert updated["documentFileId"] == replacement.file_id
    assert "更新需求" in files.storage.read_text(replacement.object_key)
    await service(files).delete("owner", result["requirementId"])
    with pytest.raises(AppError):
        await files.download("viewer", image.file_id)


@pytest.mark.parametrize("raw", [b"<p><br></p>", b"<script>bad()</script>", b"\xff"])
async def test_invalid_html_never_becomes_ready(files, raw):
    row, _ = await upload(files, raw, "requirement.html")
    with pytest.raises(AppError):
        await files.complete("owner", row.file_id)
    assert row.status == "pending"


async def test_replayed_upload_cannot_replace_sanitized_html(files):
    row, _ = await upload(files, b"<p>safe</p><script>bad()</script>", "requirement.html")
    await files.complete("owner", row.file_id)
    files.storage.client.put_object(Bucket=row.bucket, Key=row.staging_key, Body=b"<p>changed</p>")
    await files.complete("owner", row.file_id)
    assert files.storage.read_text(row.object_key) == "<p>safe</p>"


async def test_cross_project_image_cannot_attach_and_old_source_is_preserved(files):
    image, _ = await upload(files, b"\x89PNG\r\n\x1a\nimage", "screen.png", "attachment")
    await files.complete("owner", image.file_id)
    image.project_id = "q"
    await files.session.commit()
    row, _ = await upload(
        files, f'<img data-file-id="{image.file_id}">'.encode(), "requirement.html"
    )
    await files.complete("owner", row.file_id)
    image_id, file_id = image.file_id, row.file_id
    with pytest.raises(AppError):
        await service(files).update(
            "owner", "r", UpdateRequirementRequest(documentType="richtext", documentFileId=file_id)
        )
    await files.session.rollback()
    assert (await files.get(file_id)).status == "ready"
    assert (await files.get(image_id)).status == "ready"
    original = await RequirementRepository(files.session).get_active_by_id("r")
    assert original.document_type == "text"
    assert original.document_file_id == ""


def test_table_structure_survives_and_unsafe_attributes_are_removed():
    from testing_agent.domain.rich_text import sanitize_rich_text

    raw = '<table style="color:red"><tbody><tr><th colspan="2">标题</th></tr>'
    raw += '<tr><td rowspan="2" onclick="bad()">内容</td><td>预期</td></tr></tbody></table>'
    clean = sanitize_rich_text(raw)
    assert '<th colspan="2">标题</th>' in clean
    assert '<td rowspan="2">内容</td>' in clean
    assert "<table><tbody><tr>" in clean
    assert "style" not in clean and "onclick" not in clean
    assert sanitize_rich_text('<td colspan="' + "1" * 5000 + '">正文</td>') == "<td>正文</td>"

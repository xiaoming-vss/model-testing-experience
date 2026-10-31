"""Materialize images submitted with a stage revision for multimodal model input."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from testing_agent_ai_worker.platform.http_client import PlatformHttpClient

MAX_REVISION_ATTACHMENTS = 6

_FILE_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def parse_revision_attachments(config: dict) -> list[dict[str, str]]:
    """Read the frozen attachment metadata from an attempt config snapshot."""
    value = config.get("revisionAttachments") or []
    if not isinstance(value, list) or len(value) > MAX_REVISION_ATTACHMENTS:
        raise ValueError("继续优化图片数量不合法")
    attachments: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("继续优化图片引用不合法")
        file_id = str(item.get("fileId") or "").strip()
        if not _FILE_ID.fullmatch(file_id):
            raise ValueError("继续优化图片引用不合法")
        attachments.append(
            {
                "fileId": file_id,
                "filename": str(item.get("filename") or "").strip()[:255],
            }
        )
    return attachments


@dataclass(slots=True)
class PlatformRevisionAttachmentDownloader:
    """Fetch revision images through short-lived platform tickets."""

    client: PlatformHttpClient
    worker_id: str

    def download(
        self, *, task_id: str, workspace: Path, attachments: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        directory = workspace / "revision-attachments"
        for attachment in attachments:
            file_id = attachment["fileId"]
            endpoint = (
                f"/internal/ai-worker/tasks/{quote(task_id, safe='')}/revision-attachments/"
                f"{quote(file_id, safe='')}?workerId={quote(self.worker_id, safe='')}"
            )
            data = self.client.get_signed_file_bytes(endpoint)
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                suffix = ".png"
            elif data.startswith(b"\xff\xd8\xff"):
                suffix = ".jpg"
            else:
                raise ValueError("继续优化图片不是 PNG/JPEG")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / (file_id + suffix)
            path.write_bytes(data)
            path.chmod(0o600)
            images.append(
                {
                    "fileId": file_id,
                    "filename": attachment["filename"],
                    "sourcePath": str(path),
                    "sourceLocation": f"/v1/files/{file_id}/download",
                }
            )
        return images

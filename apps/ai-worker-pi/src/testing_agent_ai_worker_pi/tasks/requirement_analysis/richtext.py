"""Materialize HTML image references without exposing signed URLs to the model."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from testing_agent_ai_worker_pi.models.task import Task
from testing_agent_ai_worker_pi.platform.http_client import PlatformHttpClient


class ImageReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.file_ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        file_id = dict(attrs).get("data-file-id") or ""
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", file_id):
            raise ValueError("富文本图片缺少有效文件引用")
        if file_id not in self.file_ids:
            self.file_ids.append(file_id)


def download_images(
    client: PlatformHttpClient, worker_id: str, source: Path, task: Task
) -> list[dict[str, str]]:
    parser = ImageReferences()
    parser.feed(source.read_text(encoding="utf-8"))
    images = []
    for file_id in parser.file_ids:
        endpoint = (
            f"/internal/ai-worker/tasks/{quote(task.task_id, safe='')}/requirement-images/"
            f"{file_id}?workerId={quote(worker_id, safe='')}"
        )
        data = client.get_signed_file_bytes(endpoint)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            suffix = ".png"
        elif data.startswith(b"\xff\xd8\xff"):
            suffix = ".jpg"
        else:
            raise ValueError("富文本关联图片不是 PNG/JPEG")
        path = source.parent / "images" / (file_id + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        images.append(
            {
                "fileId": file_id,
                "sourcePath": str(path),
                "sourceLocation": f"/v1/files/{file_id}/download",
            }
        )
    return images

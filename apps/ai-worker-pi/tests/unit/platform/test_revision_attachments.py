import tempfile
import unittest
from pathlib import Path

from testing_agent_ai_worker_pi.platform.revision_attachments import (
    PlatformRevisionAttachmentDownloader,
    parse_revision_attachments,
)


class _Client:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.paths: list[str] = []

    def get_signed_file_bytes(self, path: str) -> bytes:
        self.paths.append(path)
        return self.data


class RevisionAttachmentTests(unittest.TestCase):
    def test_parses_frozen_attachment_metadata(self):
        self.assertEqual(
            parse_revision_attachments(
                {"revisionAttachments": [{"fileId": "image-1", "filename": "login.png"}]}
            ),
            [{"fileId": "image-1", "filename": "login.png"}],
        )
        self.assertEqual(parse_revision_attachments({}), [])

    def test_rejects_invalid_attachment_metadata(self):
        for value in (
            "image",
            [{"fileId": "../escape"}],
            [{"fileId": "image-1", "filename": "x"}] * 7,
            [{"filename": "missing.png"}],
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_revision_attachments({"revisionAttachments": value})

    def test_downloads_png_through_task_scoped_ticket(self):
        client = _Client(b"\x89PNG\r\n\x1a\nrest")
        with tempfile.TemporaryDirectory() as directory:
            images = PlatformRevisionAttachmentDownloader(client, "worker").download(
                task_id="task",
                workspace=Path(directory),
                attachments=[{"fileId": "image-1", "filename": "login.png"}],
            )
            self.assertEqual(
                client.paths,
                ["/internal/ai-worker/tasks/task/revision-attachments/image-1?workerId=worker"],
            )
            self.assertEqual(images[0]["fileId"], "image-1")
            self.assertEqual(images[0]["filename"], "login.png")
            self.assertEqual(Path(images[0]["sourcePath"]).read_bytes(), b"\x89PNG\r\n\x1a\nrest")
            self.assertEqual(Path(images[0]["sourcePath"]).stat().st_mode & 0o777, 0o600)

    def test_rejects_non_image_payload(self):
        client = _Client(b"not an image")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                PlatformRevisionAttachmentDownloader(client, "worker").download(
                    task_id="task",
                    workspace=Path(directory),
                    attachments=[{"fileId": "image-1", "filename": "login.png"}],
                )


if __name__ == "__main__":
    unittest.main()

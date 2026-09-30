from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from test_worker.control_plane.artifacts import ArtifactUploader


def test_artifacts_use_private_signed_upload_and_stable_references(tmp_path):
    path = tmp_path / "shot.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    calls = []

    def request(method, endpoint, body):
        calls.append((endpoint, body))
        if endpoint.endswith("/uploads"):
            return {
                "fileId": "f",
                "upload": {
                    "url": "https://s3.test/upload",
                    "fields": {"policy": "signed"},
                },
            }
        return {"fileId": "f", "path": "/v1/files/f/download"}

    def s3(request):
        assert "X-Worker-Token" not in request.headers
        assert "Authorization" not in request.headers
        assert b"PNG" in request.read()
        return httpx.Response(204)

    original = httpx.Client
    with patch(
        "test_worker.control_plane.artifacts.httpx.Client",
        side_effect=lambda **kw: original(transport=httpx.MockTransport(s3), **kw),
    ):
        uploader = ArtifactUploader(
            SimpleNamespace(artifacts_root_dir=str(tmp_path), worker_id="w"), request
        )
        result = uploader.publish("t", {"stepResults": [{"screenshotPath": str(path)}]})
        assert result["stepResults"][0]["screenshotPath"] == "/v1/files/f/download"
        assert (
            uploader.publish("t", {"tracePath": str(path)})["tracePath"]
            == "/v1/files/f/download"
        )
        assert len(calls) == 2
        assert path.exists()
        uploader.cleanup("t")
        assert not path.exists()


def test_failed_artifact_upload_preserves_original_and_does_not_complete(tmp_path):
    path = tmp_path / "trace.zip"
    path.write_bytes(b"zip")
    calls = []

    def request(method, endpoint, body):
        calls.append(endpoint)
        return {
            "fileId": "f",
            "upload": {"url": "https://s3.test/upload", "fields": {}},
        }

    original = httpx.Client
    with patch(
        "test_worker.control_plane.artifacts.httpx.Client",
        side_effect=lambda **kw: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(403)), **kw
        ),
    ):
        uploader = ArtifactUploader(
            SimpleNamespace(artifacts_root_dir=str(tmp_path), worker_id="w"), request
        )
        with pytest.raises(ValueError, match="S3"):
            uploader.publish("t", {"tracePath": str(path)})
        uploader.cleanup("t")
        assert path.exists()
        assert len(calls) == 1
        with pytest.raises(ValueError, match="outside"):
            uploader.upload("t", str(tmp_path.parent / "outside"))

from __future__ import annotations

import httpx

from test_worker.core.artifact_server import ArtifactHttpServer, build_artifact_url


def test_build_artifact_url_uses_path_relative_to_artifacts_root(tmp_path) -> None:
    screenshot = tmp_path / "run 1" / "step 1.png"

    url = build_artifact_url(
        str(screenshot),
        str(tmp_path),
        "http://worker-a:9010/",
    )

    assert url == "http://worker-a:9010/run%201/step%201.png"


def test_artifact_http_server_serves_files_and_disables_directory_listing(tmp_path) -> None:
    screenshot = tmp_path / "run-1" / "step-1.png"
    screenshot.parent.mkdir()
    screenshot.write_bytes(b"fake-png")
    trace = tmp_path / "run-1" / "trace.zip"
    trace.write_bytes(b"private-trace")
    server = ArtifactHttpServer(str(tmp_path), "127.0.0.1", 0)
    server.start()

    try:
        response = httpx.get(f"http://127.0.0.1:{server.port}/run-1/step-1.png")
        directory_response = httpx.get(f"http://127.0.0.1:{server.port}/run-1/")
        trace_response = httpx.get(f"http://127.0.0.1:{server.port}/run-1/trace.zip")
    finally:
        server.stop()

    assert response.status_code == 200
    assert response.content == b"fake-png"
    assert response.headers["access-control-allow-origin"] == "*"
    assert directory_response.status_code == 404
    assert trace_response.status_code == 404

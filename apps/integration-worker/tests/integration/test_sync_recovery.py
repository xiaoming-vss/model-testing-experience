import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
HELPER = Path(__file__).resolve().parents[1] / "helpers/control_plane.py"
CONTENT = b"isolated-image"
INSTANCE = "http://zentao.fixture/sub"


class Remote:
    def __init__(self):
        self.bug = None
        self.writes = []
        self.tokens = []
        self.calls = []
        self.upload_delay = 0
        self.failure = ""

    def tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_zentao_instance":
            return {
                "schemaVersion": 1,
                "instanceUrl": INSTANCE,
                "apiBaseUrl": INSTANCE + "/api.php/v2",
            }
        if name == "get_executions_executionID":
            return {"execution": {"id": 20, "project": 10}}
        if name == "get_stories_storyID":
            return {"story": {"id": 30, "product": 40}}
        if name == "get_executions_executionID_stories":
            return {"stories": [{"id": 30}]}
        if name == "get_users":
            return {"users": [{"id": 1, "account": "dev", "type": "inside"}], "total": 1}
        if name == "get_bugs_bugID":
            return {"bug": dict(self.bug)}
        self.writes.append(name)
        if name == "post_bugs":
            payload = arguments["payload"]
            self.bug = {
                "id": 50,
                **payload,
                "product": payload["productID"],
                "files": [],
                "assignedTo": payload.get("assignedTo", ""),
            }
            if self.failure == "create-uncertain":
                raise ValueError("isolated response loss after creation")
            return {"status": "success", "id": 50}
        if name == "upload_bug_attachment":
            with urllib.request.urlopen(arguments["downloadUrl"], timeout=3) as response:
                downloaded = response.read()
            assert len(downloaded) == arguments["size"]
            assert hashlib.sha256(downloaded).hexdigest() == arguments["sha256"]
            time.sleep(self.upload_delay)
            self.bug["files"] = [
                {
                    "id": 101,
                    "objectType": "bug",
                    "objectID": 50,
                    "extension": "png",
                    "url": INSTANCE + "/file-read-101.png",
                }
            ]
            return {"status": "success", "id": 101}
        if name == "put_bugs_bugID":
            self.bug.update(arguments["payload"])
            return {"status": "success"}
        raise AssertionError("Unexpected fixture tool")


@pytest.fixture
def remote():
    state = Remote()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(CONTENT)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.tokens.append(self.headers.get("token"))
            if body["method"] == "notifications/initialized":
                self.send_response(202)
                self.end_headers()
                return
            if body["method"] == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
            else:
                try:
                    result = {
                        "structuredContent": state.tool(
                            body["params"]["name"], body["params"]["arguments"]
                        )
                    }
                except ValueError:
                    self.send_response(503)
                    self.end_headers()
                    return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state, f"http://127.0.0.1:{server.server_port}/mcp"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def cp(tmp_path, remote, request):
    cp_root = ROOT / "apps/control-plane"
    interpreter = cp_root / ".venv/bin/python"
    if not interpreter.exists():
        pytest.skip("Cross-process CP fixture requires the control-plane dev environment")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    info = tmp_path / "info.json"
    config = tmp_path / "cp.toml"
    config.write_text(
        '[security.jwt]\nkey="disposable-jwt-key-for-http-fixture-only"\n'
        '[security.integration]\nkey="disposable-cipher-key"\n'
        '[data.db.user]\ndsn="sqlite+aiosqlite:///' + str(tmp_path / "cp.db") + '"\n'
    )
    log = (tmp_path / "cp.log").open("w+")
    mode = getattr(request, "param", "")
    command = [
        str(interpreter),
        str(HELPER),
        "--db",
        str(tmp_path / "cp.db"),
        "--port",
        str(port),
        "--mcp",
        remote[1],
        "--info",
        str(info),
    ]
    if mode:
        command.append("--" + mode)
    process = subprocess.Popen(
        command,
        cwd=cp_root,
        env={**os.environ, "PYTHONPATH": str(cp_root / "src"), "APP_CONF": str(config)},
        stdout=log,
        stderr=log,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            if process.poll() is not None:
                log.seek(0)
                pytest.fail("Disposable CP failed to start: " + log.read())
            try:
                if httpx.get(url + "/v1/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("Disposable CP health timeout")
        yield url, {"Authorization": "Bearer " + json.loads(info.read_text())["token"]}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()


def start_worker(url, directory):
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / "worker.toml"
    config.write_text(
        "[control_plane]\nbase_url=" + json.dumps(url) + "\n"
        'worker_token="integration-fixture-key"\n[worker]\n'
        "poll_interval_seconds=0.05\nheartbeat_interval_seconds=0.25\n"
        "lease_margin_seconds=0.1\n"
        "health_file=" + json.dumps(str(directory / "health.json")) + "\n"
        "evidence_file=" + json.dumps(str(directory / "evidence.json")) + "\n"
    )
    log = (directory / "worker.log").open("w+")
    process = subprocess.Popen(
        [sys.executable, "-m", "testing_agent_integration_worker.main", "--config", str(config)],
        cwd=ROOT / "apps/integration-worker",
        stdout=log,
        stderr=log,
    )
    return process, log


async def stop_worker(process, log):
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait)
        pytest.fail("Worker did not finish its bounded SIGTERM drain")
    finally:
        log.close()


async def run_to_terminal(cp, tmp_path, *, upload_delay=0, fields=None, replicas=1, job_id=None):
    url, headers = cp
    async with httpx.AsyncClient(base_url=url) as client:
        if job_id is None:
            path = "zentao-field-update-jobs" if fields is not None else "zentao-sync-jobs"
            submitted = await client.post(
                "/v1/bugs/bug/" + path,
                headers=headers,
                json={"requestId": uuid4().hex, **(fields or {})},
            )
            assert submitted.status_code == 202, submitted.text
            job_id = submitted.json()["data"]["jobId"]
        workers = [start_worker(url, tmp_path / f"replica-{i}") for i in range(replicas)]
        try:
            async with asyncio.timeout(30 + upload_delay):
                while True:
                    for process, log in workers:
                        if process.poll() is not None:
                            log.seek(0)
                            pytest.fail("Independent Worker exited: " + log.read())
                    response = await client.get(
                        f"/v1/bugs/bug/zentao-jobs/{job_id}", headers=headers
                    )
                    assert response.status_code == 200, response.text
                    result = response.json()["data"]
                    if result["jobStatus"] not in {"queued", "claimed", "running"}:
                        return result
                    await asyncio.sleep(0.05)
        finally:
            for process, log in workers:
                await stop_worker(process, log)


async def fields_request(cp, *, desired="dev"):
    url, headers = cp
    async with httpx.AsyncClient(base_url=url) as client:
        response = await client.get("/v1/bugs/bug/zentao-push", headers=headers)
        assert response.status_code == 200, response.text
        target = response.json()["data"]["target"]
    return {
        "expectedTarget": target,
        "expectedRemoteBugId": 50,
        "expectedOpenedBuild": ["trunk"],
        "expectedAssignedTo": "",
        "openedBuild": ["trunk"],
        "assignedTo": desired,
    }


@pytest.mark.parametrize("cp", ["", "lost-result"], indirect=True)
async def test_owned_http_fixture_executes_full_sync_once_and_recovers_result_loss(
    cp, remote, tmp_path
):
    result = await run_to_terminal(cp, tmp_path)
    assert result["jobStatus"] == "succeeded", result
    assert remote[0].writes == ["post_bugs", "upload_bug_attachment", "put_bugs_bugID"]
    assert (
        remote[0].bug["steps"]
        == '<p>evidence<img src="http://zentao.fixture/sub/file-read-101.png" ></p>'
    )
    assert set(remote[0].tokens) == {"actor-secret"}


@pytest.mark.parametrize("cp", ["lost-prepare"], indirect=True)
async def test_lost_prepare_never_repeats_or_starts_the_remote_write(cp, remote, tmp_path):
    result = await run_to_terminal(cp, tmp_path)
    assert result["jobStatus"] == "unknown", result
    assert remote[0].writes == []


async def test_long_upload_keeps_heartbeats_separate_from_execution(cp, remote, tmp_path):
    remote[0].upload_delay = 12
    result = await run_to_terminal(cp, tmp_path, upload_delay=12)
    assert result["jobStatus"] == "succeeded", result
    assert remote[0].writes.count("upload_bug_attachment") == 1


async def test_uncertain_creation_is_applied_once_and_blocks_dependent_writes(cp, remote, tmp_path):
    remote[0].failure = "create-uncertain"
    result = await run_to_terminal(cp, tmp_path)
    assert result["jobStatus"] == "unknown", result
    assert remote[0].bug["id"] == 50
    assert remote[0].writes == ["post_bugs"]


async def test_fields_update_writes_only_changed_fields_and_reads_back(cp, remote, tmp_path):
    assert (await run_to_terminal(cp, tmp_path))["jobStatus"] == "succeeded"
    request = await fields_request(cp)
    remote[0].calls.clear()
    result = await run_to_terminal(cp, tmp_path, fields=request)
    assert result["jobStatus"] == "succeeded", result
    writes = [args for name, args in remote[0].calls if name == "put_bugs_bugID"]
    assert writes == [{"bugID": 50, "payload": {"assignedTo": "dev"}}]
    assert remote[0].calls[-1][0] == "get_bugs_bugID"


async def test_fields_update_rejects_changed_preview_without_writing(cp, remote, tmp_path):
    assert (await run_to_terminal(cp, tmp_path))["jobStatus"] == "succeeded"
    request = await fields_request(cp)
    remote[0].bug["assignedTo"] = "external-edit"
    remote[0].writes.clear()
    result = await run_to_terminal(cp, tmp_path, fields=request)
    assert result["jobStatus"] == "failed", result
    assert remote[0].writes == []
    assert remote[0].bug["assignedTo"] == "external-edit"


async def test_two_independent_workers_execute_each_remote_step_once(cp, remote, tmp_path):
    remote[0].upload_delay = 1
    result = await run_to_terminal(cp, tmp_path, replicas=2)
    assert result["jobStatus"] == "succeeded", result
    assert remote[0].writes == ["post_bugs", "upload_bug_attachment", "put_bugs_bugID"]


async def test_sigterm_drains_inflight_upload_and_restart_does_not_repeat_it(cp, remote, tmp_path):
    url, headers = cp
    remote[0].upload_delay = 12
    async with httpx.AsyncClient(base_url=url) as client:
        response = await client.post(
            "/v1/bugs/bug/zentao-sync-jobs", headers=headers, json={"requestId": uuid4().hex}
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["data"]["jobId"]
        directory = tmp_path / "replica-0"
        process, log = start_worker(url, directory)
        try:
            async with asyncio.timeout(10):
                while "upload_bug_attachment" not in remote[0].writes:
                    await asyncio.sleep(0.05)
            check = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "testing_agent_integration_worker.main", "--healthcheck"],
                env={**os.environ, "APP_CONF": str(directory / "worker.toml")},
                capture_output=True,
                timeout=3,
            )
            assert check.returncode == 0
            process.terminate()
            assert await asyncio.to_thread(process.wait, timeout=15) == 0
            result = (
                await client.get(f"/v1/bugs/bug/zentao-jobs/{job_id}", headers=headers)
            ).json()["data"]
            assert result["result"]["steps"] == {
                "create_bug": "succeeded",
                "upload_attachment:image": "succeeded",
                "update_description": "pending",
            }
            assert remote[0].writes == ["post_bugs", "upload_bug_attachment"]
            assert not (directory / "health.json").exists()
        finally:
            await stop_worker(process, log)
    result = await run_to_terminal(cp, tmp_path, job_id=job_id)
    assert result["jobStatus"] == "succeeded", result
    assert remote[0].writes == ["post_bugs", "upload_bug_attachment", "put_bugs_bugID"]


@pytest.mark.parametrize("cp", ["offline-results"], indirect=True)
async def test_crash_outbox_replay_acknowledges_a_manually_recovered_original_fact(
    cp, remote, tmp_path
):
    url, headers = cp
    directory = tmp_path / "replica-0"
    async with httpx.AsyncClient(base_url=url) as client:
        submitted = await client.post(
            "/v1/bugs/bug/zentao-sync-jobs", headers=headers, json={"requestId": uuid4().hex}
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["data"]["jobId"]
        process, log = start_worker(url, directory)
        journal = directory / "evidence.json"
        try:
            async with asyncio.timeout(15):
                while not journal.exists() or not json.loads(journal.read_text()):
                    await asyncio.sleep(0.05)
            evidence = json.loads(journal.read_text())[0]
            assert evidence["event"]["result"] == {"remoteBugId": 50}
            assert "actor-secret" not in journal.read_text()
            assert "X-Amz-Signature" not in journal.read_text()
            process.kill()
            await asyncio.to_thread(process.wait, timeout=3)
            async with asyncio.timeout(20):
                while True:
                    response = await client.get(
                        f"/v1/bugs/bug/zentao-jobs/{job_id}", headers=headers
                    )
                    if response.json()["data"]["jobStatus"] == "unknown":
                        break
                    await asyncio.sleep(0.1)
        finally:
            await stop_worker(process, log)
        recovered = await client.post(
            "/v1/bugs/bug/zentao-push/reconcile", headers=headers, json={"remoteBugId": 50}
        )
        assert recovered.status_code == 200, recovered.text
        (tmp_path / "resume-results").touch()
        process, log = start_worker(url, directory)
        try:
            async with asyncio.timeout(10):
                while json.loads(journal.read_text()):
                    await asyncio.sleep(0.05)
            assert remote[0].writes == ["post_bugs"]
            response = await client.get(f"/v1/bugs/bug/zentao-jobs/{job_id}", headers=headers)
            assert response.json()["data"]["jobStatus"] == "partial"
        finally:
            await stop_worker(process, log)
    resumed = await run_to_terminal(cp, tmp_path)
    assert resumed["jobStatus"] == "succeeded", resumed
    assert remote[0].writes == ["post_bugs", "upload_bug_attachment", "put_bugs_bugID"]

"""Explicit 180-second transport acceptance; no production services or credentials."""

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime
from statistics import median
from uuid import uuid4

import httpx
import pytest
from test_sync_recovery import cp as cp
from test_sync_recovery import remote as remote
from test_sync_recovery import start_worker, stop_worker


def percentile95(values):
    return sorted(values)[max(0, int(len(values) * 0.95) - 1)]


@pytest.mark.skipif(
    os.environ.get("MTX_INTEGRATION_LONG_UPLOAD") != "1",
    reason="Set MTX_INTEGRATION_LONG_UPLOAD=1 for the 180-second isolated acceptance",
)
async def test_upload_timeout_keeps_heartbeats_and_ordinary_business_available(
    cp, remote, tmp_path
):
    url, headers = cp
    state = remote[0]
    # Exceed the actual upload RPC deadline; one external write must become unknown.
    state.upload_delay = 180.5
    directory = tmp_path / "worker"
    baseline, during, heartbeat_values = [], [], []
    paths = ("/v1/bugs/bug", "/v1/projects/project")
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=5, trust_env=False
    ) as client:

        async def ordinary_samples(output):
            for path in paths:
                began = time.monotonic()
                response = await client.get(path)
                output.append(time.monotonic() - began)
                assert response.status_code == 200, response.text

        for _ in range(10):
            await ordinary_samples(baseline)
        submitted_at = time.monotonic()
        submitted = await client.post(
            "/v1/bugs/bug/zentao-sync-jobs", json={"requestId": uuid4().hex}
        )
        submit_seconds = time.monotonic() - submitted_at
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["data"]["jobId"]
        worker, log = start_worker(url, directory)
        try:
            async with asyncio.timeout(205):
                while "upload_bug_attachment" not in state.writes:
                    assert worker.poll() is None
                    await asyncio.sleep(0.1)
                upload_started = time.monotonic()
                while True:
                    await ordinary_samples(during)
                    with sqlite3.connect(tmp_path / "cp.db") as connection:
                        value = connection.execute(
                            "SELECT heartbeat_at FROM integration_jobs WHERE job_id=?", (job_id,)
                        ).fetchone()[0]
                        heartbeat_values.append(datetime.fromisoformat(value))
                    status = await client.get(f"/v1/bugs/bug/zentao-jobs/{job_id}")
                    assert status.status_code == 200
                    result = status.json()["data"]
                    if result["jobStatus"] not in {"queued", "claimed", "running"}:
                        break
                    assert worker.poll() is None
                    await asyncio.sleep(3)
                upload_seconds = time.monotonic() - upload_started
            assert result["jobStatus"] == "unknown", result
            assert result["result"]["steps"]["upload_attachment:image"] == "unknown"
            assert result["result"]["steps"]["update_description"] == "blocked"
            assert upload_seconds >= 178
            assert len(set(heartbeat_values)) >= 50
            assert (heartbeat_values[-1] - heartbeat_values[0]).total_seconds() >= 175
            gaps = [
                (b - a).total_seconds()
                for a, b in zip(heartbeat_values, heartbeat_values[1:], strict=False)
            ]
            assert max(gaps) < 10  # The fixture's real lease is ten seconds.
            assert percentile95(during) < max(1, percentile95(baseline) * 8)
            assert submit_seconds < 1
            # Allow the single timed-out fixture write to finish; no replay or dependent write.
            await asyncio.sleep(3)
            assert state.writes == ["post_bugs", "upload_bug_attachment"]
            report = {
                "transport": "independent HTTP MCP fixture; SQLite protocol fixture",
                "submitSeconds": submit_seconds,
                "uploadSeconds": upload_seconds,
                "baselineMedianSeconds": median(baseline),
                "baselineP95Seconds": percentile95(baseline),
                "duringMedianSeconds": median(during),
                "duringP95Seconds": percentile95(during),
                "ordinaryRequestsDuringUpload": len(during),
                "distinctHeartbeats": len(set(heartbeat_values)),
                "maxObservedHeartbeatGapSeconds": max(gaps),
                "jobStatus": result["jobStatus"],
                "externalWrites": state.writes,
            }
            proof = tmp_path / "long-upload-acceptance.json"
            proof.write_text(json.dumps(report, indent=2))
            proof.chmod(0o600)
        finally:
            await stop_worker(worker, log)

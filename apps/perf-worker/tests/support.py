"""Shared test helpers."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

from testing_agent_perf_worker.compiler.compiler import CompiledPlan
from testing_agent_perf_worker.contracts.spec import RemoteWriteAuth, RemoteWriteSpec
from testing_agent_perf_worker.core.config import Settings
from testing_agent_perf_worker.runner.workspace import Workspace

FAKE_VERSION = "2.3.0"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def base_spec_dict() -> dict[str, Any]:
    return {
        "specVersion": "1.0",
        "runId": "run-001",
        "case": {
            "name": "case",
            "steps": [
                {
                    "name": "ping",
                    "method": "GET",
                    "path": "/ping",
                    "checks": [{"type": "status", "op": "eq", "value": 200}],
                }
            ],
            "load": {"model": "vus", "vus": 1, "duration": "1s"},
            "acceptance": {
                "source": "user_confirmed",
                "confirmed": True,
                "criteria": {"http_req_failed": ["rate<0.01"]},
            },
        },
        "environment": {
            "baseUrl": "http://127.0.0.1:18080",
            "variables": {},
        },
        "remoteWrite": {"url": "http://127.0.0.1:19090/api/v1/write"},
        "limits": {"maxDurationSeconds": 30, "stopGraceSeconds": 5},
    }


def spec_with(**overrides: Any) -> dict[str, Any]:
    spec = copy.deepcopy(base_spec_dict())
    for key, value in overrides.items():
        spec[key] = value
    return spec


def make_settings(tmp_path: Path, fake_k6: Path) -> Settings:
    settings = Settings()
    settings.k6.binary = str(fake_k6)
    settings.k6.expected_version = FAKE_VERSION
    settings.runner.workspace_root = str(tmp_path / "runs")
    settings.runner.max_duration_seconds = 30
    settings.runner.stop_grace_seconds = 2
    settings.runner.max_data_file_mb = 5
    settings.runner.max_summary_mb = 5
    return settings


def write_fake_k6(
    tmp_path: Path,
    name: str,
    run_body: str,
    version: str = FAKE_VERSION,
) -> Path:
    script = tmp_path / name
    script.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

if len(sys.argv) > 1 and sys.argv[1] == "version":
    print("k6 v{version} (fake)")
    sys.exit(0)

{run_body}
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def fake_pass_body() -> str:
    return """
Path("summary.json").write_text(
    json.dumps({"metrics": {"http_reqs": {"type": "counter", "values": {"count": 1}}}})
)
sys.exit(0)
"""


def fake_threshold_body() -> str:
    return """
Path("summary.json").write_text(
    json.dumps({"metrics": {"http_req_duration": {"type": "trend", "values": {"p(95)": 999}}}})
)
sys.exit(99)
"""


def fake_error_body() -> str:
    return """
print("level=error msg=\\"boom\\"", file=sys.stderr, flush=True)
sys.exit(1)
"""


def fake_sleep_body() -> str:
    return """
print("sleeping", file=sys.stderr, flush=True)
time.sleep(30)
sys.exit(0)
"""


def make_compiled_plan(workspace: Workspace, **overrides: Any) -> CompiledPlan:
    plan = CompiledPlan(
        run_id="run-001",
        plan_path=workspace.plan_path,
        script_path=workspace.script_path,
        plan={},
        env_values={"tenant": "tenant-secret"},
        remote_write=RemoteWriteSpec(
            url="http://127.0.0.1:19090/api/v1/write",
            auth=RemoteWriteAuth(type="basic", username="writer", password="rw-secret"),
        ),
        max_duration_seconds=5,
        stop_grace_seconds=1,
        template_version="1.0.0",
        script_sha256="abc",
    )
    return dataclasses.replace(plan, **overrides)

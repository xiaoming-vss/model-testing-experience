from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from support import FIXTURES, base_spec_dict

from testing_agent_perf_worker.compiler.compiler import compile_run_spec
from testing_agent_perf_worker.contracts.spec import RunSpec, load_run_spec
from testing_agent_perf_worker.core.config import Settings
from testing_agent_perf_worker.core.errors import CompileError
from testing_agent_perf_worker.runner.workspace import Workspace


def _compile(
    tmp_path: Path,
    data: dict[str, Any],
    *,
    spec_dir: Path | None = None,
    files: dict[str, str] | None = None,
) -> tuple[Any, Workspace]:
    base = spec_dir or tmp_path
    for name, content in (files or {}).items():
        (base / name).write_text(content, encoding="utf-8")
    spec = RunSpec.model_validate(data)
    settings = Settings()
    settings.runner.workspace_root = str(tmp_path / "runs")
    workspace = Workspace.create(Path(settings.runner.workspace_root), spec.run_id)
    return compile_run_spec(spec, base, workspace.root, settings), workspace


def test_compile_fixture(tmp_path: Path) -> None:
    spec = load_run_spec(FIXTURES / "case.yaml")
    settings = Settings()
    settings.runner.workspace_root = str(tmp_path / "runs")
    workspace = Workspace.create(Path(settings.runner.workspace_root), spec.run_id)

    compiled = compile_run_spec(spec, FIXTURES, workspace.root, settings)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "constant-arrival-rate"
    assert scenario["rate"] == 2
    assert scenario["preAllocatedVUs"] == 2
    assert compiled.plan["envKeys"] == ["tenant"]
    assert compiled.env_values == {"tenant": "perf-tenant"}
    assert compiled.plan["steps"][0]["extract"][0]["from"] == "json"
    assert compiled.plan["data"][0]["rowCount"] == 2

    plan_text = compiled.plan_path.read_text(encoding="utf-8")
    assert "perf-tenant" not in plan_text
    assert "secret-001" not in plan_text
    data_text = (workspace.data_dir / "users.json").read_text(encoding="utf-8")
    assert "secret-001" in data_text

    script = (workspace.root / "main.js").read_bytes()
    assert compiled.script_sha256 == hashlib.sha256(script).hexdigest()


def test_vus_constant_scenario(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {"model": "vus", "vus": 3, "duration": "2s"}

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "constant-vus"
    assert scenario["vus"] == 3


def test_vus_ramp_scenario(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "vus",
        "vus": 3,
        "duration": "2s",
        "rampUp": "1s",
        "rampDown": "1s",
    }

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "ramping-vus"
    assert scenario["startVUs"] == 0
    assert [stage["target"] for stage in scenario["stages"]] == [3, 3, 0]


def test_request_rate_scenario(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "request_rate",
        "rate": 10,
        "timeUnit": "1s",
        "duration": "2s",
        "preAllocatedVUs": 1,
        "maxVUs": 3,
    }

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "constant-arrival-rate"
    assert scenario["rate"] == 10


def test_staged_vus_step_scenario(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "staged_vus",
        "profile": "step",
        "stages": [
            {"target": 10, "ramp": "5s", "hold": "30s"},
            {"target": 30, "ramp": "5s", "hold": "30s"},
            {"target": 60, "ramp": "5s", "hold": "60s"},
        ],
        "finalDown": "10s",
    }

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "ramping-vus"
    assert scenario["startVUs"] == 0
    assert scenario["stages"] == [
        {"duration": "5s", "target": 10},
        {"duration": "30s", "target": 10},
        {"duration": "5s", "target": 30},
        {"duration": "30s", "target": 30},
        {"duration": "5s", "target": 60},
        {"duration": "60s", "target": 60},
        {"duration": "10s", "target": 0},
    ]


def test_staged_vus_spike_scenario_keeps_baseline_and_zero_hold_is_skipped(
    tmp_path: Path,
) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "staged_vus",
        "profile": "spike",
        "stages": [
            {"target": 5, "ramp": "0s", "hold": "30s"},
            {"target": 50, "ramp": "5s", "hold": "10s"},
            {"target": 5, "ramp": "5s", "hold": "30s"},
        ],
        "finalDown": "0s",
    }

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["executor"] == "ramping-vus"
    assert scenario["startVUs"] == 0
    assert scenario["stages"] == [
        {"duration": "0s", "target": 5},
        {"duration": "30s", "target": 5},
        {"duration": "5s", "target": 50},
        {"duration": "10s", "target": 50},
        {"duration": "5s", "target": 5},
        {"duration": "30s", "target": 5},
    ]


def test_staged_vus_zero_hold_is_skipped(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "staged_vus",
        "stages": [{"target": 10, "ramp": "1s", "hold": "0s"}],
    }

    compiled, _ = _compile(tmp_path, data)

    scenario = compiled.plan["options"]["scenarios"]["main"]
    assert scenario["stages"] == [{"duration": "1s", "target": 10}]


def test_future_variable_is_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["steps"] = [
        {
            "name": "profile",
            "method": "GET",
            "path": "/profile",
            "headers": {"Authorization": "Bearer {{var.token}}"},
        }
    ]

    with pytest.raises(CompileError, match="尚未提取"):
        _compile(tmp_path, data)


def test_missing_data_column_is_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["data"] = [
        {"name": "users", "source": "users.csv", "strategy": "unique_per_iteration"}
    ]
    data["case"]["steps"][0]["body"] = {"username": "{{data.password}}"}

    with pytest.raises(CompileError, match="不存在的数据列"):
        _compile(
            tmp_path,
            data,
            files={"users.csv": "username\nuser-1\n"},
        )


def test_missing_environment_variable_is_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["steps"][0]["headers"] = {"X-Tenant": "{{env.missing}}"}

    with pytest.raises(CompileError, match="不存在的环境变量"):
        _compile(tmp_path, data)


def test_builtin_placeholders_are_allowed(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["steps"][0]["body"] = {
        "id": "{{uuid}}",
        "createdAt": "{{timestamp}}",
        "iteration": "{{iteration}}",
        "vu": "{{vu}}",
    }

    compiled, _ = _compile(tmp_path, data)

    assert compiled.plan["steps"][0]["body"]["id"] == "{{uuid}}"


def test_data_path_traversal_is_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["data"] = [
        {"name": "users", "source": "../outside.csv", "strategy": "unique_per_iteration"}
    ]

    with pytest.raises(CompileError, match="运行规格目录内"):
        _compile(tmp_path, data)


def test_none_content_type_with_body_is_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["steps"][0]["contentType"] = "none"
    data["case"]["steps"][0]["body"] = {"name": "value"}

    with pytest.raises(CompileError, match="contentType=none"):
        _compile(tmp_path, data)


def test_duplicate_data_columns_are_rejected(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["data"] = [
        {"name": "a", "source": "a.csv", "strategy": "unique_per_iteration"},
        {"name": "b", "source": "b.csv", "strategy": "unique_per_iteration"},
    ]
    data["case"]["steps"][0]["body"] = {"id": "{{data.id}}"}

    with pytest.raises(CompileError, match="重复"):
        _compile(
            tmp_path,
            data,
            files={
                "a.csv": "id\n1\n",
                "b.csv": "id\n2\n",
            },
        )


def test_inline_data_rows_are_written(tmp_path: Path) -> None:
    data = base_spec_dict()
    data["case"]["data"] = [
        {
            "name": "users",
            "rows": [{"username": "u-1"}, {"username": "u-2"}],
            "strategy": "unique_per_iteration",
        }
    ]
    data["case"]["steps"][0]["body"] = {"username": "{{data.username}}"}

    compiled, workspace = _compile(tmp_path, data)

    assert compiled.plan["data"][0]["rowCount"] == 2
    payload = (workspace.data_dir / "users.json").read_text(encoding="utf-8")
    assert "u-1" in payload and "u-2" in payload

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from support import FIXTURES, base_spec_dict

from testing_agent_perf_worker.contracts.spec import (
    ExtractSource,
    RunSpec,
    load_run_spec,
)
from testing_agent_perf_worker.core.errors import SpecError


def test_yaml_fixture_loads() -> None:
    spec = load_run_spec(FIXTURES / "case.yaml")

    assert spec.run_id == "fixture-run-001"
    assert spec.case.load.model == "arrival_rate"
    assert spec.case.steps[0].extract[0].source is ExtractSource.JSON
    assert spec.case.data[0].source == "users.csv"


def test_json_fixture_loads() -> None:
    spec = load_run_spec(FIXTURES / "snapshot.json")

    assert spec.run_id == "fixture-json-001"
    assert spec.case.load.model == "vus"


def test_unknown_fields_are_rejected() -> None:
    data = base_spec_dict()
    data["extra"] = True

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_unknown_load_model_is_rejected() -> None:
    data = base_spec_dict()
    data["case"]["load"] = {"model": "unknown", "duration": "1s"}

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_request_rate_rejects_multi_step() -> None:
    data = base_spec_dict()
    data["case"]["steps"].append({"name": "second", "method": "GET", "path": "/second"})
    data["case"]["load"] = {
        "model": "request_rate",
        "rate": 10,
        "timeUnit": "1s",
        "duration": "1s",
        "preAllocatedVUs": 1,
        "maxVUs": 2,
    }

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_model_suggested_cannot_be_confirmed() -> None:
    data = base_spec_dict()
    data["case"]["acceptance"]["source"] = "model_suggested"
    data["case"]["acceptance"]["confirmed"] = True

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_user_confirmed_requires_criteria() -> None:
    data = base_spec_dict()
    data["case"]["acceptance"]["criteria"] = {}

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_missing_acceptance_cannot_have_criteria() -> None:
    data = base_spec_dict()
    data["case"]["acceptance"]["source"] = "missing"
    data["case"]["acceptance"]["confirmed"] = False
    data["case"]["acceptance"]["criteria"] = {"checks": ["rate>0.99"]}

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


@pytest.mark.parametrize("name", ["K6_FOO", "PATH", "HOME", "1BAD"])
def test_reserved_environment_names_are_rejected(name: str) -> None:
    data = base_spec_dict()
    data["environment"]["variables"] = {name: "value"}

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_base_url_rejects_credentials() -> None:
    data = base_spec_dict()
    data["environment"]["baseUrl"] = "http://user:pass@example.com"

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_ramp_pair_is_required() -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "vus",
        "vus": 2,
        "duration": "1s",
        "rampUp": "1s",
    }

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_preallocated_vus_alias_is_accepted() -> None:
    data = base_spec_dict()
    data["case"]["load"] = {
        "model": "arrival_rate",
        "rate": 2,
        "timeUnit": "1s",
        "duration": "1s",
        "preAllocatedVUs": 2,
        "maxVUs": 5,
    }

    spec = RunSpec.model_validate(data)

    assert spec.case.load.pre_allocated_vus == 2
    assert spec.case.load.max_vus == 5


def test_yaml_duplicate_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("specVersion: '1.0'\nspecVersion: '1.0'\n", encoding="utf-8")

    with pytest.raises(SpecError, match="重复键"):
        load_run_spec(path)


def test_json_duplicate_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"specVersion": "1.0", "specVersion": "1.0"}', encoding="utf-8")

    with pytest.raises(SpecError, match="重复键"):
        load_run_spec(path)


def test_unquoted_yaml_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "case.yaml"
    path.write_text(
        "specVersion: 1.0\nrunId: run-1\n",
        encoding="utf-8",
    )

    with pytest.raises(SpecError):
        load_run_spec(path)


def test_unsupported_spec_version_is_rejected() -> None:
    data = base_spec_dict()
    data["specVersion"] = "2.0"

    with pytest.raises(ValidationError):
        RunSpec.model_validate(data)


def test_spec_json_round_trip() -> None:
    data = base_spec_dict()
    spec = RunSpec.model_validate(data)
    payload = json.loads(spec.model_dump_json(by_alias=True))

    assert payload["specVersion"] == "1.0"
    assert payload["case"]["load"]["model"] == "vus"

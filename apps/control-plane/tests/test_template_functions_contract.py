"""The pre-rendered request snapshot follows the same template contract as the Worker."""

import json
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from testing_agent.domain import template_functions as functions
from testing_agent.services.api_request_render import (
    render_api_case_request,
    render_template_string,
)

# Shared with the api-ui-worker: the snapshot a run starts with must match the
# request the Worker later renders from the same template.
CONTRACT = Path(__file__).resolve().parents[3] / "tests/fixtures/api-template-contract.json"


@pytest.fixture
def frozen(monkeypatch):
    """Freeze the clock, uuid and randomness to the values the contract fixture describes."""
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))["frozen"]
    text = spec["randomText"]
    monkeypatch.setattr(
        functions,
        "time",
        SimpleNamespace(
            time=lambda: spec["epoch"],
            gmtime=lambda: time.gmtime(spec["epoch"]),
            strftime=time.strftime,
        ),
    )
    monkeypatch.setattr(
        functions,
        "datetime",
        SimpleNamespace(now=lambda: datetime.strptime(spec["localNow"], "%Y-%m-%d %H:%M:%S")),
    )
    monkeypatch.setattr(functions, "uuid", SimpleNamespace(uuid4=lambda: spec["uuid"]))
    monkeypatch.setattr(
        functions,
        "random",
        SimpleNamespace(
            randint=lambda low, high: spec["randomInt"],
            choices=lambda alphabet, k: list(text * (k // len(text) + 1))[:k],
        ),
    )


def test_pre_render_follows_the_shared_contract(frozen):
    for case in json.loads(CONTRACT.read_text(encoding="utf-8"))["cases"]:
        assert render_template_string(case["template"], case.get("vars", {})) == case["expected"]


def test_request_snapshot_renders_functions_as_text(frozen):
    api_case = SimpleNamespace(
        method="POST",
        url_template="/orders/{{$uuid}}",
        headers_json={"X-Trace": "{{$uuid}}"},
        query_json={"at": "{{$now}}"},
        body_type="json",
        body_json={"trace": "{{$uuid}}", "at": "{{$timestamp}}", "count": 2, "flag": True},
        body_text="",
    )
    environment = SimpleNamespace(base_url="https://api.example.test")

    rendered = render_api_case_request(api_case, environment, [])

    identifier = "3f2a9c1e-7b4d-4e8a-9c06-5d1b2a7e4f30"
    assert rendered.snapshot == {
        "method": "POST",
        "url": f"https://api.example.test/orders/{identifier}",
        "headersJson": f'{{"X-Trace":"{identifier}"}}',
        "queryJson": '{"at":"2026-11-23T04:22:03Z"}',
        "bodyType": "json",
        # A function is text, exactly as the Worker sends it; other JSON types pass through.
        "body": f'{{"trace":"{identifier}","at":"1795407723","count":2,"flag":true}}',
    }

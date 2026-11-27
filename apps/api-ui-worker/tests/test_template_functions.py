"""Built-in template functions: one evaluator behind the API and UI runtimes."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_worker import template_functions as functions
from test_worker.api import template_runtime
from test_worker.api.case_runner import build_request
from test_worker.ui.templates import RenderContext, render_field

# Shared with the control plane: every runtime must produce what the fixture says.
CONTRACT = (
    Path(__file__).resolve().parents[3] / "tests/fixtures/api-template-contract.json"
)


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
        SimpleNamespace(
            now=lambda: datetime.strptime(spec["localNow"], "%Y-%m-%d %H:%M:%S")
        ),
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


def api_render(template: str, variables: dict[str, str]) -> str:
    return template_runtime.render_template(template, variables)


def ui_render(template: str, variables: dict[str, str]) -> str:
    return render_field(
        template, variables, RenderContext("operationValue", "", "input", {})
    )


@pytest.mark.parametrize("renderer", [api_render, ui_render], ids=["api", "ui"])
def test_functions_follow_the_shared_contract(frozen, renderer):
    # The UI runtime rejects undefined variables instead of leaving them in place.
    cases = [
        case
        for case in json.loads(CONTRACT.read_text(encoding="utf-8"))["cases"]
        if renderer is api_render or case.get("ui", True)
    ]
    assert cases
    for case in cases:
        assert renderer(case["template"], case.get("vars", {})) == case["expected"], (
            case["name"]
        )


def test_api_request_renders_functions_in_every_part_with_one_value_each(frozen):
    request_snapshot, request = build_request(
        {
            "requestTemplate": {
                "method": "post",
                "baseUrl": "https://api.example.test",
                "urlTemplate": "/orders/{{$uuid}}",
                "headersJson": '{"X-Trace":"{{$uuid}}"}',
                "queryJson": '{"at":"{{$now}}"}',
                "bodyType": "json",
                "bodyJson": '{"trace":"{{$uuid}}","seq":2,"flag":true}',
            }
        },
        {},
    )

    identifier = "3f2a9c1e-7b4d-4e8a-9c06-5d1b2a7e4f30"
    assert request_snapshot == {
        "method": "POST",
        "url": f"https://api.example.test/orders/{identifier}",
        "headersJson": f'{{"X-Trace":"{identifier}"}}',
        "queryJson": '{"at":"2026-11-23T04:22:03Z"}',
        "bodyType": "json",
        "body": f'{{"trace":"{identifier}","seq":2,"flag":true}}',
    }
    assert request["method"] == "POST"
    assert request["json"] == {"trace": identifier, "seq": 2, "flag": True}
    assert "{{" not in json.dumps(request_snapshot)


def test_api_request_sent_before_this_change_left_functions_unexpanded(frozen):
    """A uuid used to go out literally as {{ $uuid }} in the real request."""
    _, request = build_request(
        {
            "requestTemplate": {
                "method": "GET",
                "baseUrl": "https://api.example.test",
                "urlTemplate": "/users/{{$uuid}}",
                "bodyType": "none",
            }
        },
        {},
    )

    assert (
        request["url"]
        == "https://api.example.test/users/3f2a9c1e-7b4d-4e8a-9c06-5d1b2a7e4f30"
    )


def test_extract_rule_default_values_accept_functions(frozen):
    assert (
        template_runtime.render_template("fallback-{{$timestamp}}", {})
        == "fallback-1795407723"
    )


def test_malformed_function_arguments_are_rejected():
    with pytest.raises(ValueError):
        api_render("{{$randomInt low high}}", {})
    with pytest.raises(ValueError):
        api_render("{{$randomString many}}", {})

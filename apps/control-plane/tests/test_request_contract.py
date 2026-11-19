"""Request models reject undeclared fields and keep update field semantics explicit."""

import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel, ValidationError
from support.project_api import account as account
from support.project_api import api as api

import testing_agent.schemas as schemas

# Historical AI task protocols carry task-specific payload fields validated
# downstream. They keep extra="allow"; every other request model forbids extras.
_AI_TASK_REASON = "AI task payload fields are validated by the task domain"
REQUEST_EXTRA_EXCEPTIONS = {
    f"testing_agent.schemas.ai_generate_task.{name}": _AI_TASK_REASON
    for name in (
        "AiGenerateTaskRunRequest",
        "CodeRiskAnalysisRunRequest",
        "CodeRiskAnalysisTaskRequest",
        "RepositoryProfileRunRequest",
        "RepositoryProfileTaskRequest",
        "TestReportGenerateTaskRunRequest",
    )
}


def request_models():
    for info in pkgutil.walk_packages(schemas.__path__, schemas.__name__ + "."):
        module = importlib.import_module(info.name)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__ or not name.endswith("Request"):
                continue
            if issubclass(obj, BaseModel):
                yield f"{module.__name__}.{name}", obj


def test_request_models_forbid_undeclared_fields_except_documented_protocols():
    strict = []
    exceptions = []
    unexpected = []
    for qualified, model in request_models():
        extra = model.model_config.get("extra")
        if qualified in REQUEST_EXTRA_EXCEPTIONS:
            exceptions.append(qualified)
            assert extra == "allow", qualified
        elif extra == "forbid":
            strict.append(qualified)
        else:
            unexpected.append(f"{qualified}: extra={extra!r}")
    assert not unexpected, "\n".join(unexpected)
    assert set(exceptions) == set(REQUEST_EXTRA_EXCEPTIONS)
    assert len(strict) > 100


def test_request_extra_exceptions_have_reasons():
    assert all(reason.strip() for reason in REQUEST_EXTRA_EXCEPTIONS.values())


def test_strict_request_rejects_unknown_field():
    from testing_agent.schemas.project import CreateProjectRequest

    with pytest.raises(ValidationError) as rejected:
        CreateProjectRequest(name="project", unknownField=True)
    assert rejected.value.errors()[0]["type"] == "extra_forbidden"


def test_http_unknown_request_field_returns_400(api):
    _, headers = account(api, "contract-owner")
    response = api.post(
        "/v1/projects",
        headers=headers,
        json={"name": "contract-project", "unknownField": True},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 400


def test_project_patch_keeps_omitted_field_and_rejects_null(api):
    _, headers = account(api, "patch-owner")
    created = api.post(
        "/v1/projects",
        headers=headers,
        json={"name": "patch-project", "description": "keep me"},
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["data"]["projectId"]

    renamed = api.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"name": "renamed-project"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["description"] == "keep me"

    cleared = api.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"description": ""},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["description"] == ""

    rejected = api.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"description": None},
    )
    assert rejected.status_code == 400, rejected.text

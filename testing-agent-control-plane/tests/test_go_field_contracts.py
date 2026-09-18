from datetime import UTC, datetime
from types import SimpleNamespace

from testing_agent.models.requirement import Requirement
from testing_agent.schemas.api_case import ApiCaseRequest, ApiCaseResponse
from testing_agent.schemas.api_run import ApiCaseRunResponse, ApiCollectionRunResponse
from testing_agent.schemas.project import ProjectResponse
from testing_agent.schemas.requirement import (
    CreateRequirementRequest,
    RequirementResponse,
)
from testing_agent.schemas.sprint import (
    CreateSprintRequest,
    SprintResponse,
)
from testing_agent.schemas.ui_run import UiCaseRunResponse
from testing_agent.schemas.ui_test_suite import UiSuiteRequest, UiSuiteResponse
from testing_agent.schemas.workers import (
    WorkerClaimRequest,
    WorkerProgressRequest,
    WorkerTaskEventRequest,
)
from testing_agent.services.integration_connection import dump_connection
from testing_agent.services.resource_binding import dump_binding
from testing_agent.services.sprint_daily_metrics import dump_metric


def test_context_schemas_use_go_fields_only():
    assert ProjectResponse(
        projectId="p1",
        userId="u1",
        name="project",
        description="desc",
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
    ).model_dump(by_alias=True) == {
        "role": "owner",
        "permissions": [],
        "projectId": "p1",
        "userId": "u1",
        "name": "project",
        "description": "desc",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }

    sprint_body = CreateSprintRequest.model_validate(
        {
            "name": "sprint",
            "description": "desc",
            "startTime": "2026-01-01T00:00:00Z",
            "endTime": "2026-01-15T00:00:00Z",
        }
    )
    assert sprint_body.start_time == datetime(2026, 1, 1, tzinfo=UTC)
    assert "status" not in CreateSprintRequest.model_json_schema()["properties"]

    assert SprintResponse(
        sprintId="s1",
        projectId="p1",
        name="sprint",
        description="desc",
        status="running",
        startTime="2026-01-01T00:00:00Z",
        endTime="2026-01-15T00:00:00Z",
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
    ).model_dump(by_alias=True) == {
        "sprintId": "s1",
        "projectId": "p1",
        "name": "sprint",
        "description": "desc",
        "status": "running",
        "startTime": "2026-01-01T00:00:00Z",
        "endTime": "2026-01-15T00:00:00Z",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def test_requirement_document_fields_match_go_contract():
    body = CreateRequirementRequest.model_validate(
        {
            "name": "req",
            "documentType": "text",
            "documentContent": "content",
        }
    )

    assert body.document_type == "text"
    assert body.document_content == "content"
    assert "description" not in CreateRequirementRequest.model_json_schema()["properties"]
    assert RequirementResponse(
        requirementId="r1",
        sprintId="s1",
        name="req",
        documentType="text",
        documentContent="content",
        documentFilename="requirement.txt",
        documentHash="hash",
        documentDownloadUrl="/v1/requirements/r1/download",
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
    ).model_dump(by_alias=True) == {
        "requirementId": "r1",
        "sprintId": "s1",
        "name": "req",
        "documentType": "text",
        "documentContent": "content",
        "documentFilename": "requirement.txt",
        "documentHash": "hash",
        "documentDownloadUrl": "/v1/requirements/r1/download",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }

    assert not hasattr(Requirement, "document_content_type")
    assert not hasattr(Requirement, "document_size")
    assert not hasattr(Requirement, "description")
    assert not hasattr(Requirement, "status")


def test_api_case_json_fields_are_strings_like_go_contract():
    body = ApiCaseRequest.model_validate(
        {
            "name": "case",
            "method": "POST",
            "urlTemplate": "/api/ping",
            "headersJson": '{"Content-Type":"application/json"}',
            "queryJson": '{"q":"1"}',
            "bodyJson": '{"name":"demo"}',
        }
    )

    assert body.headers_json == '{"Content-Type":"application/json"}'
    assert body.query_json == '{"q":"1"}'
    assert body.body_json == '{"name":"demo"}'

    response = ApiCaseResponse(
        caseId="case1",
        collectionId="collection1",
        name="case",
        method="POST",
        urlTemplate="/api/ping",
        headersJson={"Content-Type": "application/json"},
        queryJson={"q": "1"},
        bodyJson={"name": "demo"},
    ).model_dump(by_alias=True)

    assert response["headersJson"] == '{"Content-Type": "application/json"}'
    assert response["queryJson"] == '{"q": "1"}'
    assert response["bodyJson"] == '{"name": "demo"}'


def test_ui_run_response_uses_snapshot_and_step_results_fields():
    payload = UiCaseRunResponse(
        runId="run1",
        caseId="case1",
        suiteId="suite1",
        requirementId="req1",
        sprintId="sprint1",
        projectId="project1",
        triggerUserId="u1",
        triggerType="manual",
        status="success",
        success=True,
        errorMessage="",
        durationMs=12,
        snapshot={"runId": "run1"},
        stepResults=[{"status": "success"}],
        startedAt="2026-01-01T00:00:00Z",
        finishedAt="2026-01-01T00:00:01Z",
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:01Z",
    ).model_dump(by_alias=True)

    assert "snapshot" in payload
    assert "stepResults" in payload
    assert "snapshotJson" not in payload
    assert "stepResultsJson" not in payload
    assert "currentUrl" not in payload
    assert "tracePath" not in payload


def test_ui_suite_screenshot_policy_uses_go_field():
    request = UiSuiteRequest(
        name="UI Suite",
        screenshotPolicy="after_each_step",
    )

    assert request.screenshot_policy == "after_each_step"

    payload = UiSuiteResponse(
        suiteId="suite1",
        requirementId="req1",
        name="UI Suite",
        screenshotPolicy="never",
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:01Z",
    ).model_dump(by_alias=True)

    assert payload["screenshotPolicy"] == "never"
    assert "screenshot_policy" not in payload


def test_worker_event_accepts_api_complete_fields_from_go_contract():
    assert WorkerClaimRequest.model_validate({"workerId": "w1"}).worker_id == "w1"

    body = WorkerTaskEventRequest.model_validate(
        {
            "workerId": "w1",
            "status": "success",
            "request": {"method": "GET"},
            "response": {"statusCode": 200},
            "runtimeVarsJson": {"token": "abc"},
            "extractResults": [{"success": True}],
            "assertResults": [{"success": True}],
        }
    )

    assert body.request == {"method": "GET"}
    assert body.response == {"statusCode": 200}
    assert body.runtime_vars_json == {"token": "abc"}
    assert body.extract_results == [{"success": True}]
    assert body.assert_results == [{"success": True}]


def test_worker_ai_json_text_fields_parse_to_json_values():
    progress = WorkerProgressRequest.model_validate(
        {
            "workerId": "w1",
            "configJson": '{"enhancedText":"需求"}',
            "resultSummaryJson": '{"status":"running"}',
        }
    )
    completed = WorkerTaskEventRequest.model_validate(
        {
            "workerId": "w1",
            "status": "success",
            "configJson": '{"caseNames":{"categories":[]}}',
            "resultSummaryJson": '{"status":"success"}',
        }
    )

    assert progress.config_json == {"enhancedText": "需求"}
    assert progress.result_summary_json == {"status": "running"}
    assert completed.config_json == {"caseNames": {"categories": []}}
    assert completed.result_summary_json == {"status": "success"}


def test_api_run_runtime_vars_json_serializes_as_go_string_contract():
    case_payload = ApiCaseRunResponse(
        runId="run-1",
        caseId="case-1",
        collectionId="collection-1",
        collectionRunId=None,
        environmentId="env-1",
        status="pending",
        success=False,
        errorMessage="",
        durationMs=0,
        request={
            "method": "GET",
            "url": "https://api.example.test/ping",
            "headersJson": "{}",
            "queryJson": "{}",
            "bodyType": "none",
            "body": "",
        },
        response={"statusCode": 0, "headersJson": "{}", "body": ""},
        runtimeVarsJson={"token": "abc"},
        extractResults=[],
        assertResults=[],
    ).model_dump(by_alias=True, mode="json")

    assert case_payload["runtimeVarsJson"] == '{"token":"abc"}'

    collection_payload = ApiCollectionRunResponse(
        collectionRunId="collection-run-1",
        collectionId="collection-1",
        requirementId="requirement-1",
        sprintId="sprint-1",
        projectId="project-1",
        environmentId="env-1",
        triggerUserId="user-1",
        triggerType="manual",
        status="pending",
        totalCount=1,
        successCount=0,
        failedCount=0,
        errorCount=0,
        skippedCount=0,
        runtimeVarsJson={},
        errorMessage="",
        startedAt="",
        finishedAt="",
        durationMs=0,
        createdAt="",
        updatedAt="",
    ).model_dump(by_alias=True, mode="json")

    assert collection_payload["runtimeVarsJson"] == "{}"


def test_integration_binding_and_metric_dump_match_go_contract():
    connection = SimpleNamespace(
        connection_id="c1",
        provider="llm",
        name="llm",
        base_url="https://llm.example",
        auth_type="api_key",
        account="",
        access_token="token",
        status="active",
        extra_json={"modelId": "gpt-test"},
        last_auth_at=None,
        last_auth_error="",
        created_at=None,
        updated_at=None,
    )
    dumped_connection = dump_connection(connection)
    assert dumped_connection["hasAccessToken"] is True
    assert dumped_connection["modelId"] == "gpt-test"
    assert "extraJson" not in dumped_connection

    binding = SimpleNamespace(
        binding_id="b1",
        instance_url="https://zentao.example",
        provider="zentao",
        connection_id="c1",
        local_resource_type="project",
        local_resource_id="p1",
        remote_resource_type="project",
        remote_resource_id="101",
        remote_parent_id="",
        remote_name_snapshot="Remote",
        status="active",
        bound_at=None,
        last_verified_at=None,
        created_at=None,
        updated_at=None,
    )
    dumped_binding = dump_binding(binding)
    assert {"bindingId", "remoteResourceType", "createdAt"} <= set(dumped_binding)
    assert "extraJson" not in dumped_binding

    metric = SimpleNamespace(
        project_id="p1",
        sprint_id="s1",
        snapshot_date="2026-01-01",
        function_case_total=1,
        function_case_executed=2,
        function_case_pending=3,
        function_case_success=4,
        function_case_failed=5,
        api_case_total=6,
        api_case_executed=7,
        api_case_pending=8,
        api_case_success=9,
        api_case_failed=10,
        ui_case_total=11,
        ui_case_executed=12,
        ui_case_pending=13,
        ui_case_success=14,
        ui_case_failed=15,
        bug_total=16,
        bug_resolved=17,
        bug_closed=18,
        bug_unresolved=19,
        bug_fatal=20,
        bug_serious=21,
        bug_normal=22,
        bug_suggestion=23,
        created_at=None,
        updated_at=None,
    )
    dumped_metric = dump_metric(metric)
    assert dumped_metric["function"] == {
        "total": 1,
        "executed": 2,
        "pending": 3,
        "success": 4,
        "failed": 5,
    }
    assert dumped_metric["bug"]["closed"] == 18
    assert dumped_metric["bug"]["suggestion"] == 23
    assert "functionCaseTotal" not in dumped_metric

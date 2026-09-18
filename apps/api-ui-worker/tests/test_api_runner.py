from __future__ import annotations

import asyncio

from test_worker.api.case_runner import ApiCaseRunner
from test_worker.api.collection_runner import ApiCollectionRunner


def test_api_case_runner_extracts_and_asserts(monkeypatch):
    captured_requests = []

    async def fake_execute(request, timeout_ms):
        captured_requests.append(request)
        return {
            "statusCode": 200,
            "headersJson": '{"X-Trace":"trace-1"}',
            "body": '{"data":{"token":"token-1","name":"acme","count":2}}',
        }

    monkeypatch.setattr("test_worker.api.case_runner.execute_request", fake_execute)

    snapshot = {
        "taskId": "task-1",
        "runId": "run-1",
        "caseId": "case-1",
        "collectionId": "collection-1",
        "environmentId": "env-1",
        "runtimeVarsJson": '{"tenant":"acme"}',
        "request": {
            "method": "GET",
            "url": "http://example.test/{{tenant}}",
            "headersJson": '{"X-Tenant":"{{tenant}}"}',
            "queryJson": "{}",
            "bodyType": "none",
            "body": "",
        },
        "extractRules": [{
            "extractRuleId": "extract-1",
            "name": "token",
            "enabled": True,
            "orderNo": 1,
            "source": "body_jsonpath",
            "sourceExpr": "$.data.token",
            "varKey": "sessionToken",
        }],
        "assertRules": [{
            "assertRuleId": "assert-1",
            "name": "tenant",
            "enabled": True,
            "orderNo": 1,
            "assertSource": "body_jsonpath",
            "targetExpr": "$.data.name",
            "comparator": "eq",
            "expectedValue": "{{tenant}}",
        }],
    }

    result = asyncio.run(ApiCaseRunner().run(snapshot))

    assert result["status"] == "success"
    assert result["success"] is True
    assert result["extractResults"][0]["value"] == "token-1"
    assert result["assertResults"][0]["success"] is True
    assert '"sessionToken":"token-1"' in result["runtimeVarsJson"]
    assert captured_requests[0]["url"] == "http://example.test/acme"


def test_api_collection_runner_reuses_extracted_runtime_vars(monkeypatch):
    captured_requests = []

    async def fake_execute(request, timeout_ms):
        captured_requests.append(request)
        if request["url"].endswith("/login"):
            return {
                "statusCode": 200,
                "headersJson": "{}",
                "body": '{"data":{"token":"token-1"}}',
            }
        return {
            "statusCode": 200,
            "headersJson": "{}",
            "body": '{"ok":true}',
        }

    monkeypatch.setattr("test_worker.api.case_runner.execute_request", fake_execute)

    client = _FakeControlPlaneClient()
    snapshot = {
        "taskId": "task-1",
        "runId": "collection-run-1",
        "collectionRunId": "collection-run-1",
        "collectionId": "collection-1",
        "items": [
            {
                "itemId": "item-1",
                "enabled": True,
                "continueOnFailure": False,
                "caseRun": _case_snapshot("case-1", "http://example.test/login", "{}", [{
                    "extractRuleId": "extract-1",
                    "name": "token",
                    "enabled": True,
                    "orderNo": 1,
                    "source": "body_jsonpath",
                    "sourceExpr": "$.data.token",
                    "varKey": "sessionToken",
                }]),
            },
            {
                "itemId": "item-2",
                "enabled": True,
                "continueOnFailure": False,
                "caseRun": _case_snapshot(
                    "case-2",
                    "http://example.test/profile",
                    '{"X-Session":"old-token"}',
                    [],
                    request_template={
                        "method": "GET",
                        "baseUrl": "http://example.test",
                        "urlTemplate": "/profile",
                        "headersJson": '{"X-Session":"{{sessionToken}}"}',
                        "queryJson": "{}",
                        "bodyType": "none",
                        "bodyJson": "",
                        "bodyText": "",
                        "timeoutMs": 5000,
                    },
                ),
            },
        ],
    }

    result = asyncio.run(ApiCollectionRunner(client).run(snapshot))

    assert result["status"] == "success"
    assert captured_requests[1]["headers"]["X-Session"] == "token-1"
    assert [item["status"] for item in client.completed_items] == ["success", "success"]


def _case_snapshot(
    case_id: str,
    url: str,
    headers_json: str,
    extract_rules: list[dict],
    request_template: dict | None = None,
):
    snapshot = {
        "taskId": "task-1",
        "runId": "",
        "collectionRunId": "collection-run-1",
        "collectionId": "collection-1",
        "caseId": case_id,
        "environmentId": "env-1",
        "runtimeVarsJson": "{}",
        "request": {
            "method": "GET",
            "url": url,
            "headersJson": headers_json,
            "queryJson": "{}",
            "bodyType": "none",
            "body": "",
        },
        "extractRules": extract_rules,
        "assertRules": [],
    }
    if request_template is not None:
        snapshot["requestTemplate"] = request_template
    return snapshot


class _FakeControlPlaneClient:
    def __init__(self):
        self.completed_items = []

    def report_api_collection_item_started(self, task_id, item_id, payload):
        return None

    def report_api_collection_item_completed(self, task_id, item_id, payload):
        self.completed_items.append(payload)

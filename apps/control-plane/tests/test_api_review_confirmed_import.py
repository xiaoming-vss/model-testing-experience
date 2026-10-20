from datetime import UTC, datetime

from support.api_review_confirmed_import import (
    ImportRepository as ImportRepository,
)
from support.api_review_confirmed_import import (
    ReviewRepository as ReviewRepository,
)
from support.api_review_confirmed_import import (
    approved_import_run as approved_import_run,
)
from support.api_review_confirmed_import import (
    import_client as import_client,
)
from support.api_review_confirmed_import import (
    make_run as make_run,
)
from support.api_review_confirmed_import import (
    review_client as review_client,
)

from testing_agent.app import create_app
from testing_agent.models.api_case import ApiCase


def test_api_candidate_edit_and_confirmed_import_routes_are_public():
    paths = create_app().openapi()["paths"]

    assert "patch" in paths["/v1/api-case-generate-task-runs/{runId}/result"]
    assert "post" in paths["/v1/api-case-generate-task-runs/{runId}/import"]


def test_api_candidate_can_be_edited_then_approval_freezes_without_importing():
    run = make_run()
    repository = ReviewRepository(run)
    client = review_client(repository)
    candidate = """cases:
  - name: Login
    method: GET
    urlTemplate: /login
"""

    saved = client.patch(
        "/v1/api-case-generate-task-runs/run-1/result",
        json={"resultYaml": candidate},
    )
    approved = client.post(
        "/v1/api-case-generate-task-runs/run-1/review",
        json={"action": "approve", "reviewComment": "looks good"},
    )
    frozen = client.patch(
        "/v1/api-case-generate-task-runs/run-1/result",
        json={"resultYaml": "cases: []"},
    )

    assert saved.status_code == 200
    assert saved.json()["data"]["resultYaml"] == candidate
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "approved"
    assert approved.json()["data"]["importStatus"] == "pending"
    assert approved.json()["data"]["importedTargets"] == []
    assert frozen.status_code == 400
    assert run.result_yaml == candidate
    assert repository.commits == 2


def test_only_successful_api_run_can_be_approved():
    run = make_run(status="failed")
    client = review_client(ReviewRepository(run))

    response = client.post(
        "/v1/api-case-generate-task-runs/run-1/review",
        json={"action": "approve"},
    )

    assert response.status_code == 400
    assert run.review_status == "pending"


def test_api_import_previews_full_conflict_then_confirms_in_place_and_only_once():
    run = approved_import_run()
    repository = ImportRepository(run)
    client = import_client(repository)

    preview = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1"},
    )
    before = client.get("/v1/api-collections/collection-1/cases")
    confirmed = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1", "confirmOverwrite": True},
    )
    after = client.get("/v1/api-collections/collection-1/cases")
    repeated = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1", "confirmOverwrite": True},
    )

    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["requiresConfirmation"] is True
    assert preview_data["run"]["reviewStatus"] == "approved"
    assert preview_data["run"]["importStatus"] == "pending"
    assert len(preview_data["conflicts"]) == 1
    conflict = preview_data["conflicts"][0]
    assert conflict["normalizedName"] == "login"
    assert conflict["existingCase"] == {
        "name": "Login",
        "description": "old description",
        "enabled": True,
        "orderNo": 1,
        "method": "GET",
        "urlTemplate": "/old-login",
        "headers": {"X-Version": "old"},
        "query": {"old": "query"},
        "bodyType": "json",
        "bodyJson": {"old": True},
        "bodyText": "",
        "timeoutMs": 1000,
        "continueOnFailure": False,
        "extractRules": [
            {
                "name": "old token",
                "enabled": True,
                "orderNo": 0,
                "source": "body_jsonpath",
                "sourceExpr": "$.old",
                "varKey": "token",
                "defaultValue": "old",
            }
        ],
        "assertRules": [
            {
                "name": "old status",
                "enabled": True,
                "orderNo": 0,
                "assertSource": "status_code",
                "targetExpr": "",
                "comparator": "eq",
                "expectedValue": "201",
            }
        ],
    }
    assert conflict["generatedCase"]["headers"] == {"X-Version": "new"}
    assert conflict["generatedCase"]["query"] == {"page": "1"}
    assert conflict["generatedCase"]["bodyJson"] == {"username": "alice"}
    assert conflict["generatedCase"]["extractRules"][0]["sourceExpr"] == "$.token"
    assert conflict["generatedCase"]["assertRules"][0]["expectedValue"] == "200"
    assert before.json()["data"]["total"] == 1
    assert before.json()["data"]["items"][0]["urlTemplate"] == "/old-login"

    assert confirmed.status_code == 200
    confirmed_data = confirmed.json()["data"]
    assert confirmed_data["requiresConfirmation"] is False
    assert confirmed_data["run"]["reviewStatus"] == "approved"
    assert confirmed_data["run"]["importStatus"] == "imported"
    assert confirmed_data["run"]["importedTargets"] == [
        {"targetType": "api_collection", "targetId": "collection-1"}
    ]
    items = after.json()["data"]["items"]
    assert len(items) == 2
    updated = next(item for item in items if item["name"] == "login")
    assert updated["caseId"] == "case-existing"
    assert updated["urlTemplate"] == "/new-login"
    assert repeated.status_code == 400


def test_api_import_enforces_target_ownership():
    repository = ImportRepository(approved_import_run(), owner="user-2")
    client = import_client(repository)

    response = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1"},
    )

    assert response.status_code == 403
    assert repository.cases[0].url_template == "/old-login"


def test_confirmed_api_import_rechecks_current_conflict_and_preserves_current_case_id():
    repository = ImportRepository(approved_import_run())
    client = import_client(repository)

    preview = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1"},
    )
    repository.cases[0].name = "Renamed old case"
    current = ApiCase(
        case_id="case-current",
        collection_id="collection-1",
        name="LOGIN",
        description="created after preview",
        enabled=True,
        order_no=2,
        method="GET",
        url_template="/current-login",
        headers_json={},
        query_json={},
        body_type="none",
        body_json=None,
        body_text="",
        timeout_ms=5000,
        continue_on_failure=False,
    )
    current.created_at = datetime.now(UTC)
    current.updated_at = current.created_at
    repository.cases.append(current)

    confirmed = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1", "confirmOverwrite": True},
    )
    cases = client.get("/v1/api-collections/collection-1/cases").json()["data"]["items"]

    assert preview.status_code == 200
    assert confirmed.status_code == 200
    login = next(case for case in cases if case["name"] == "login")
    assert login["caseId"] == "case-current"
    assert any(case["name"] == "Renamed old case" for case in cases)


def test_api_import_persistence_failure_is_atomic_preserves_review_and_can_retry():
    run = approved_import_run()
    run.result_yaml = """cases:
  - name: Health
    method: GET
    urlTemplate: /health
"""
    repository = ImportRepository(run)
    repository.fail_next_commit = True
    client = import_client(repository)
    reviewed_at = run.reviewed_at

    failed = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1"},
    )
    after_failure = client.get("/v1/api-collections/collection-1/cases")
    failure_state = (
        run.review_status,
        run.reviewer_user_id,
        run.reviewed_at,
        run.import_status,
    )
    retried = client.post(
        "/v1/api-case-generate-task-runs/run-1/import",
        json={"collectionId": "collection-1"},
    )
    after_retry = client.get("/v1/api-collections/collection-1/cases")

    assert failed.status_code == 500
    assert after_failure.json()["data"]["total"] == 1
    assert failure_state == ("approved", "user-1", reviewed_at, "pending")
    assert retried.status_code == 200
    assert after_retry.json()["data"]["total"] == 2


def test_api_candidate_batch_names_are_trimmed_and_case_insensitive():
    repository = ReviewRepository(make_run())
    client = review_client(repository)

    response = client.patch(
        "/v1/api-case-generate-task-runs/run-1/result",
        json={
            "resultYaml": """cases:
  - name: Login
    method: GET
    urlTemplate: /one
  - name: " login "
    method: GET
    urlTemplate: /two
"""
        },
    )

    assert response.status_code == 400
    assert repository.run.result_yaml == "cases: []"

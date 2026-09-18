from fastapi.testclient import TestClient

from app.dependencies import get_zentao_project_service_factory
from app.main import create_app


class BrokenZentaoProjectService:
    async def list_projects(self, query):
        raise RuntimeError("boom")


def test_validation_error_returns_unified_shape(client: TestClient) -> None:
    response = client.get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com&page=0",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 422
    assert payload["code"] == 42200
    assert payload["message"] == "Request validation failed."
    assert payload["errors"]
    assert "request_id" not in payload


def test_validation_error_with_value_error_ctx_is_serialized_safely(client: TestClient) -> None:
    response = client.post(
        "/api/v1/zentao/testcases?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
        json={
            "productID": 1,
            "project": 2,
            "execution": 3,
            "cases": [
                {
                    "title": "Case with invalid expects length",
                    "steps": ["step 1", "step 2"],
                    "expects": ["expect 1"],
                }
            ],
        },
    )

    payload = response.json()
    assert response.status_code == 422
    assert payload["code"] == 42200
    assert payload["message"] == "Request validation failed."
    assert payload["errors"]
    assert payload["errors"][0]["ctx"]["error"] == "steps and expects must have the same length."
    assert "request_id" not in payload


def test_unexpected_error_returns_unified_shape() -> None:
    app = create_app()
    app.dependency_overrides[get_zentao_project_service_factory] = lambda: (
        lambda base_url, token: BrokenZentaoProjectService()
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/api/v1/zentao/projects?base_url=https://zentao.example.com",
        headers={"Authorization": "Bearer demo-token"},
    )

    payload = response.json()
    assert response.status_code == 500
    assert payload["code"] == 50000
    assert payload["message"] == "Internal server error."
    assert payload["data"] == {}
    assert "request_id" not in payload

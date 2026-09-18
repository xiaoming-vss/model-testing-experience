from fastapi.testclient import TestClient


def test_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"] == {"status": "ok"}
    assert "request_id" not in payload


def test_readiness(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "ok"
    assert payload["data"] == {"status": "ok"}
    assert "request_id" not in payload

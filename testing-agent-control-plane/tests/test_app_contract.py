from fastapi.testclient import TestClient

from testing_agent.app import create_app
from testing_agent.core.errors import ErrBadRequest, ErrSuccess, app_error_payload


def test_success_error_payload_matches_go_contract():
    assert app_error_payload(ErrSuccess, {"message": "ok"}) == {
        "code": 0,
        "message": "ok",
        "data": {"message": "ok"},
    }


def test_app_error_allows_traceback_assignment_for_asgi_cleanup():
    ErrBadRequest.__traceback__ = None


def test_root_returns_go_style_response():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": {"message": "testing-agent server is running"},
    }


def test_worker_route_rejects_invalid_token():
    client = TestClient(create_app())

    response = client.post("/internal/ui-worker/tasks/claim", json={"workerId": "worker-1"})

    assert response.status_code == 401
    assert response.json() == {"message": "未授权或登录失效"}

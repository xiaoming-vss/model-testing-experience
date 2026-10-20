from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from support.project_api import account
from support.project_api import api as api

from testing_agent.app import create_app
from testing_agent.core.config import get_settings


def test_logout_revokes_only_current_token_and_survives_backend_restart(api):
    user, first = account(api, "alice")
    response = api.post("/v1/login", json={"name": "alice", "password": "test-password"})
    second = {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}
    assert first != second

    assert api.post("/v1/logout", headers=first).status_code == 200
    assert api.get("/v1/user", headers=first).status_code == 401
    assert api.get("/v1/projects", headers=first).status_code == 401
    assert api.get("/v1/user", headers=second).json()["data"]["userId"] == user["userId"]
    assert api.post("/v1/logout", headers=first).status_code == 401

    restarted = create_app()
    restarted.dependency_overrides.update(api.app.dependency_overrides)
    client = TestClient(restarted)
    assert client.get("/v1/user", headers=first).status_code == 401
    assert client.get("/v1/user", headers=second).status_code == 200
    fresh = api.post("/v1/login", json={"name": "alice", "password": "test-password"})
    assert fresh.status_code == 200
    assert (
        api.get(
            "/v1/user", headers={"Authorization": "Bearer " + fresh.json()["data"]["accessToken"]}
        ).status_code
        == 200
    )


def test_logout_accepts_preexisting_tokens_without_jti(api):
    user, _ = account(api, "legacy")
    token = jwt.encode(
        {"userId": user["userId"], "exp": datetime.now(UTC) + timedelta(hours=1)},
        get_settings().jwt_key,
        algorithm="HS256",
    )
    headers = {"Authorization": "Bearer " + token}
    assert api.get("/v1/user", headers=headers).status_code == 200
    assert api.post("/v1/logout", headers=headers).status_code == 200
    assert api.get("/v1/user", headers=headers).status_code == 401


def test_invalid_logout_does_not_revoke_valid_sessions(api):
    user, valid = account(api, "alice")
    forged = jwt.encode(
        {"userId": user["userId"], "exp": datetime.now(UTC) + timedelta(hours=1)},
        "different-signing-key-for-test-only",
        algorithm="HS256",
    )
    expired = jwt.encode(
        {"userId": user["userId"], "exp": datetime.now(UTC) - timedelta(seconds=1)},
        get_settings().jwt_key,
        algorithm="HS256",
    )
    assert api.post("/v1/logout").status_code == 401
    for token in (forged, expired, "invalid"):
        assert (
            api.post("/v1/logout", headers={"Authorization": "Bearer " + token}).status_code == 401
        )
    assert api.get("/v1/user", headers=valid).status_code == 200


def test_logout_of_one_user_does_not_affect_other_users(api):
    _, alice = account(api, "alice")
    _, bob = account(api, "bob")
    assert api.post("/v1/logout", headers=alice).status_code == 200
    assert api.get("/v1/user", headers=alice).status_code == 401
    assert api.get("/v1/user", headers=bob).status_code == 200


def test_alternative_signature_encoding_cannot_bypass_revocation(api):
    _, headers = account(api, "alice")
    padded = {"Authorization": headers["Authorization"] + "="}
    assert api.get("/v1/user", headers=padded).status_code == 200
    assert api.post("/v1/logout", headers=headers).status_code == 200
    assert api.get("/v1/user", headers=padded).status_code == 401

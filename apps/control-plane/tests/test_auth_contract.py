import asyncio
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from testing_agent.api.deps import get_auth_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.core.security import hash_password, parse_access_token
from testing_agent.models.user import User
from testing_agent.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from testing_agent.services import auth as auth_module
from testing_agent.services.auth import AuthService


class InMemoryUserRepository:
    def __init__(self, user: User | None = None) -> None:
        self.user = user

    async def get_by_name(self, name: str) -> User | None:
        if self.user is not None and self.user.nickname == name:
            return self.user
        return None

    async def get_by_email(self, email: str) -> User | None:
        if self.user is not None and self.user.email == email:
            return self.user
        return None

    async def get_by_user_id(self, user_id: str) -> User | None:
        if self.user is not None and self.user.user_id == user_id:
            return self.user
        return None

    def add(self, user: User) -> None:
        self.user = user

    async def commit(self) -> None:
        pass

    async def refresh(self, user: User) -> None:
        pass


def auth_client(repository: InMemoryUserRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: AuthService(repository)
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    return TestClient(app, raise_server_exceptions=False)


def test_auth_requests_use_go_field_names():
    assert (
        RegisterRequest.model_validate(
            {"name": "alice", "password": "secret", "email": "a@example.com"}
        ).name
        == "alice"
    )
    assert LoginRequest.model_validate({"name": "alice", "password": "secret"}).name == "alice"
    assert UpdateProfileRequest.model_validate({"name": "new"}).name == "new"


def test_auth_responses_use_go_field_names():
    assert LoginResponse(access_token="token").model_dump(by_alias=True) == {"accessToken": "token"}
    assert UserResponse(user_id="u1", name="alice", email="a@example.com").model_dump(
        by_alias=True
    ) == {
        "userId": "u1",
        "name": "alice",
        "email": "a@example.com",
    }


def test_register_returns_the_created_user():
    response = auth_client(InMemoryUserRepository()).post(
        "/v1/register",
        json={"name": "alice", "password": "secret", "email": "a@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "userId": response.json()["data"]["userId"],
        "name": "alice",
        "email": "a@example.com",
    }


def test_registered_user_can_log_in_with_existing_password_format():
    repository = InMemoryUserRepository()
    client = auth_client(repository)
    registered = client.post("/v1/register", json={"name": "alice", "password": "secret"})

    response = client.post("/v1/login", json={"name": "alice", "password": "secret"})

    assert response.status_code == 200
    assert (
        parse_access_token(response.json()["data"]["accessToken"])
        == (registered.json()["data"]["userId"])
    )
    assert repository.user is not None
    assert repository.user.password.startswith("$2")


@pytest.mark.parametrize(
    ("name", "password"),
    [("alice", "wrong"), ("missing", "secret"), ("alice", "x" * 73), ("alice", "密" * 25)],
)
def test_login_rejects_invalid_credentials(name, password):
    user = User(user_id="user-1", nickname="alice", password=hash_password("secret"))

    response = auth_client(InMemoryUserRepository(user)).post(
        "/v1/login", json={"name": name, "password": password}
    )

    assert response.status_code == 401
    assert response.json()["code"] == 401


def test_register_rejects_password_over_bcrypt_byte_limit():
    repository = InMemoryUserRepository()

    response = auth_client(repository).post(
        "/v1/register", json={"name": "alice", "password": "密" * 25}
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400
    assert repository.user is None


@pytest.mark.parametrize("operation", ["register", "login"])
async def test_health_responds_while_password_computation_is_in_progress(monkeypatch, operation):
    user = User(user_id="user-1", nickname="alice", password="hashed")
    repository = InMemoryUserRepository(user if operation == "login" else None)
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: AuthService(repository)
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()

    def slow_password_computation(*args):
        loop.call_soon_threadsafe(started.set)
        if not release.wait(timeout=5):
            raise TimeoutError("password computation was not released")
        return True if operation == "login" else "hashed"

    monkeypatch.setattr(
        auth_module,
        "verify_password" if operation == "login" else "hash_password",
        slow_password_computation,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        request = asyncio.create_task(
            client.post(f"/v1/{operation}", json={"name": "alice", "password": "secret"})
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            assert not request.done(), "password computation blocked the event loop"
            health = await asyncio.wait_for(client.get("/v1/health"), timeout=2)
            assert health.status_code == 200
            assert health.json()["data"] == {"status": "ok"}
            assert not request.done()
        finally:
            release.set()
            response = await asyncio.wait_for(request, timeout=2)
        assert response.status_code == 200


def test_update_profile_returns_the_updated_user():
    user = User(
        user_id="user-1",
        nickname="alice",
        password="hashed",
        email="a@example.com",
    )
    response = auth_client(InMemoryUserRepository(user)).put(
        "/v1/user",
        json={"name": "alice-2", "email": "new@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "userId": "user-1",
        "name": "alice-2",
        "email": "new@example.com",
    }

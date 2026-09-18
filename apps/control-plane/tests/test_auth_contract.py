from fastapi.testclient import TestClient

from testing_agent.api.deps import get_auth_service, get_current_user_id
from testing_agent.app import create_app
from testing_agent.models.user import User
from testing_agent.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
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

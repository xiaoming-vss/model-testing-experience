"""Shared preparation for resource binding providers tests; no collected cases."""

from __future__ import annotations

from types import SimpleNamespace

from authorization_database import AuthorizationDatabase


def _request(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "provider": "zentao",
        "connectionId": "conn-1",
        "remoteResourceId": "101",
    }
    body.update(overrides)
    return body


class RecordingZentaoClient:
    session = AuthorizationDatabase()

    """gitlab 路径不得触碰禅道客户端;一旦被调用即留下记录。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def list_project_executions(self, connection, remote_id, **kwargs):
        return {"items": [{"id": 201}], "total": 1}

    async def get_project(self, connection, remote_resource_id):
        self.calls.append((connection, remote_resource_id))
        return SimpleNamespace(id=1, name="x", deleted=False)


class RecordingConnectionService:
    async def resolve_gitlab_group_id(self, connection_id, project_id, group_id, *, user_id):
        return group_id

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        return SimpleNamespace(connection_id=connection_id, base_url="https://example.test")

    async def get_active_personal(self, user_id, provider, connection_id, project_id=""):
        self.calls.append((user_id, provider, connection_id, project_id))
        return SimpleNamespace(
            connection_id=connection_id, base_url="https://example.test", access_token="token"
        )


class FakeMcpAccess:
    async def resolve(self, user_id, project_id, expected_instance=""):
        return SimpleNamespace(connection_id="conn-1", base_url="https://example.test")


class FakeRepository:
    session = AuthorizationDatabase()

    def __init__(self) -> None:
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
        )
        self.rows: list = []

    async def get_project(self, project_id):
        return self.project

    async def get_sprint(self, sprint_id):
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_requirement(self, requirement_id):
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")

    async def get_active_by_local_resource(self, resource_type, resource_id):
        from testing_agent.services.service_instance import instance_key

        if resource_type == "requirement" or (
            resource_type == "sprint" and resource_id == "local-1"
        ):
            return None
        return SimpleNamespace(
            provider="zentao",
            remote_resource_id="1",
            instance_url="https://example.test",
            instance_key=instance_key("https://example.test"),
        )

    async def exists_active_by_remote_resource(self, *args, **kwargs):
        return False

    async def get_active_project_group_binding(
        self, provider, project_id, group_id, *, for_update=False
    ):
        return next(
            (
                r
                for r in self.rows
                if r.remote_resource_type == "group" and r.remote_resource_id == group_id
            ),
            None,
        )

    async def exists_active_project_group_binding(
        self, provider, project_id, group_id, instance=""
    ):
        return False

    def add(self, binding) -> None:
        self.rows.append(binding)

    async def commit(self) -> None:
        pass

    async def refresh(self, row) -> None:
        pass

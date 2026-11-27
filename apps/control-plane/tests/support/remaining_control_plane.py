from types import SimpleNamespace

from authorization_database import AuthorizationDatabase, AuthorizedRepositoryFixture


class TaskScopeFixture(AuthorizedRepositoryFixture):
    async def get_sprint(self, sprint_id):
        assert sprint_id == "sprint-1"
        return SimpleNamespace(sprint_id=sprint_id, project_id="project-1")

    async def get_requirement(self, requirement_id):
        assert requirement_id == "requirement-1"
        return SimpleNamespace(requirement_id=requirement_id, sprint_id="sprint-1")


class FakeZentaoAccess:
    async def resolve(self, user_id, project_id, expected_instance=""):
        assert (user_id, project_id) == ("user-1", "project-1")
        return await FakeIntegrationConnectionService().get_active_personal(
            user_id, "zentao", "conn-1", project_id
        )


class FakeUpload:
    def __init__(self, content: bytes, filename: str = "cases.yaml"):
        self.content = content
        self.filename = filename

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content)
        result, self.content = self.content[:size], self.content[size:]
        return result


class FakeResourceBindingRepository:
    session = AuthorizationDatabase()

    def __init__(self):
        self.project = SimpleNamespace(
            project_id="project-1",
            user_id="user-1",
        )
        self.rows = []
        self.active_local = None
        self.remote_exists = False
        self.committed = False
        self.refreshed = None

    async def get_project(self, project_id):
        assert project_id == "project-1"
        return self.project

    async def get_active_by_local_resource(self, resource_type, resource_id):
        assert (resource_type, resource_id) == ("project", "project-1")
        return self.active_local

    async def exists_active_by_remote_resource(
        self,
        provider,
        connection_id,
        remote_resource_type,
        remote_resource_id,
        *,
        instance="",
    ):
        assert provider == "zentao"
        assert connection_id == "conn-1"
        assert remote_resource_type == "project"
        assert remote_resource_id == "101"
        return self.remote_exists

    def add(self, binding):
        self.rows.append(binding)

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        self.refreshed = row


class FakeIntegrationConnectionService:
    async def get_active_personal(self, user_id, provider, connection_id, project_id=""):
        assert user_id == "user-1"
        assert provider == "zentao"
        assert connection_id == "conn-1"
        return SimpleNamespace(
            connection_id="conn-1",
            provider="zentao",
            status="active",
            base_url="https://zentao.example",
            access_token="token",
        )


class FakeZentaoResourceClient:
    session = AuthorizationDatabase()

    def __init__(self, *, deleted=False):
        self.deleted = deleted
        self.project_calls = []

    async def get_project(self, connection, remote_resource_id):
        self.project_calls.append((connection.connection_id, remote_resource_id))
        return SimpleNamespace(
            id=101,
            name="旧禅道项目",
            deleted=self.deleted,
        )


class FakeIntegrationRepositoryForConnectionAuth:
    session = AuthorizationDatabase()

    def __init__(self):
        self.rows = []
        self.commits = 0

    async def get(self, user_id, provider, connection_id, project_id="", *, lock=False):
        return next(
            (
                row
                for row in self.rows
                if row.user_id == user_id
                and row.provider == provider
                and row.connection_id == connection_id
            ),
            None,
        )

    async def list(self, user_id, provider, project_id=""):
        return [row for row in self.rows if row.user_id == user_id and row.provider == provider]

    def add(self, connection):
        self.rows.append(connection)

    async def commit(self):
        self.commits += 1

    async def refresh(self, connection):
        return None

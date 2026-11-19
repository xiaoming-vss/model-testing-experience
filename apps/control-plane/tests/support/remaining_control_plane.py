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
    async def resolve_zentao_access(self, user_id, connection_id, project_id=""):
        return await self.get_active_personal(user_id, "zentao", connection_id, project_id)

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


class FakeIntegrationRepositoryForZentaoBrowse:
    async def get(self, user_id, provider, connection_id, project_id="", *, lock=False):
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


class FakeZentaoBrowseClient:
    def __init__(self):
        self.calls = []

    async def list_projects(self, connection, page=1, page_size=100):
        self.calls.append(("projects", connection.connection_id, page, page_size))
        return {
            "items": [
                SimpleNamespace(
                    id=101,
                    name="项目A",
                    code="PA",
                    description="desc",
                    status="doing",
                    begin="2026-01-01",
                    end="2026-02-01",
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-02T00:00:00Z",
                    deleted=False,
                ),
                SimpleNamespace(id=102, name="已删除项目", deleted=True),
            ],
            "total": 2,
        }

    async def list_project_executions(self, connection, remote_project_id, page=1, page_size=100):
        self.calls.append(
            ("executions", connection.connection_id, remote_project_id, page, page_size)
        )
        return {
            "items": [
                SimpleNamespace(
                    id=201,
                    project_id=101,
                    name="执行A",
                    description="exec desc",
                    status="doing",
                    begin="2026-01-03",
                    end="2026-01-20",
                    parent_id=0,
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_testtasks(
        self,
        connection,
        remote_execution_id,
        page=1,
        page_size=100,
    ):
        self.calls.append(
            ("testtasks", connection.connection_id, remote_execution_id, page, page_size)
        )
        return {
            "items": [
                SimpleNamespace(
                    id=301,
                    project_id=101,
                    execution_id=201,
                    name="测试单A",
                    title="测试单标题",
                    description="",
                    status="doing",
                    type="feature",
                    owner="tester",
                    opened_by="pm",
                    begin="",
                    end="",
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_stories(self, connection, remote_execution_id):
        self.calls.append(("stories", connection.connection_id, remote_execution_id))
        return {
            "items": [
                SimpleNamespace(
                    id=401,
                    title="需求A",
                    product_id=1,
                    module_id=2,
                    plan_id=3,
                    status="active",
                    stage="developing",
                    priority="2",
                    assigned_to="dev",
                    opened_by="pm",
                    created_at="",
                    updated_at="",
                    deleted=False,
                )
            ],
            "total": 1,
        }

    async def list_execution_cases(self, connection, remote_execution_id, page=1, page_size=100):
        self.calls.append(("cases", connection.connection_id, remote_execution_id, page, page_size))
        return {
            "items": [
                SimpleNamespace(
                    id="501",
                    module="模块A",
                    title="用例A",
                    preconditions="前置",
                    steps="步骤",
                    expected_results="预期",
                    priority="1",
                    case_type="feature",
                    order_no=7,
                    deleted=False,
                )
            ],
            "total": 1,
        }


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


class FakeZentaoAuthProvider:
    def __init__(self, token="token-1"):
        self.token = token
        self.calls = []

    async def authenticate(self, base_url, account, password, **kwargs):
        self.calls.append((base_url, account, password, kwargs))
        return SimpleNamespace(access_token=self.token, expires_at=None)


class FakeZentaoAuthHttpClient:
    kwargs = {}

    def __init__(self, **kwargs):
        self.__class__.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, json):
        return SimpleNamespace(
            status_code=200,
            text='{"token":"token-ssl"}',
            json=lambda: {"token": "token-ssl"},
        )

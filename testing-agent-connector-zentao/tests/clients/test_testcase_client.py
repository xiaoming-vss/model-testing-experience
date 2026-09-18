import pytest

from app.clients.zentao.testcase_client import ZentaoTestCaseClient
from app.core.exceptions import AppError
from app.core.zentao_toml import ZentaoTomlConfig


class FakeTokenManager:
    def __init__(self, token: str = "request-token") -> None:
        self.token = token
        self.get_token_calls = 0

    @property
    def is_ready(self) -> bool:
        return True

    async def get_token(self) -> str:
        self.get_token_calls += 1
        return self.token


@pytest.mark.anyio
async def test_testcase_client_create_testcase_posts_payload() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestCaseClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )
    create_payload = {
        "productID": 1,
        "title": "测试压敏模块显示是否正常",
        "module": 0,
        "story": 0,
        "pri": 3,
        "precondition": "已进入压敏模块页面",
        "steps": ["步骤1", "步骤2"],
        "expects": ["期望1", "期望2"],
        "stepType": ["step", "step"],
        "project": 2,
        "execution": 3,
    }

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, params
        assert method == "POST"
        assert path == "/testcases"
        assert headers == {"token": "request-token"}
        assert json_body == create_payload
        return {"status": "success", "id": 456}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.create_testcase(create_payload)

    assert payload["id"] == 456
    assert token_manager.get_token_calls == 1


@pytest.mark.anyio
async def test_testcase_client_list_execution_testcases_uses_execution_path() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestCaseClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, json_body
        assert method == "GET"
        assert path == "/executions/11/testcases"
        assert params == {"browseType": "all", "recPerPage": 100, "pageID": 1}
        assert headers == {"token": "request-token"}
        return {"status": "success", "testcases": [{"case": "123"}]}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.list_execution_testcases(
        11,
        params={"browseType": "all", "recPerPage": 100, "pageID": 1},
    )

    assert payload["testcases"][0]["case"] == "123"
    assert token_manager.get_token_calls == 1


@pytest.mark.anyio
async def test_testcase_client_update_testcase_puts_payload() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestCaseClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )
    update_payload = {
        "productID": 1,
        "title": "已存在用例",
        "module": 0,
        "story": 0,
        "pri": 2,
        "precondition": "前置条件",
        "steps": ["步骤1"],
        "expects": ["期望1"],
        "stepType": ["step"],
        "project": 2,
        "execution": 3,
    }

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, params
        assert method == "PUT"
        assert path == "/testcases/456"
        assert headers == {"token": "request-token"}
        assert json_body == update_payload
        return {"status": "success"}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.update_testcase(456, update_payload)

    assert payload["status"] == "success"
    assert token_manager.get_token_calls == 1


@pytest.mark.anyio
async def test_testcase_client_get_testcase_uses_detail_path() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestCaseClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del action_name, params, json_body
        assert method == "GET"
        assert path == "/testcases/123"
        assert headers == {"token": "request-token"}
        return {"status": "success", "testcase": {"id": "123", "title": "Login"}}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    payload = await client.get_testcase(123)

    assert payload["testcase"]["id"] == "123"


@pytest.mark.anyio
async def test_testcase_client_get_testcase_requires_testcase_payload() -> None:
    token_manager = FakeTokenManager()
    client = ZentaoTestCaseClient(
        ZentaoTomlConfig(base_url="https://zentao.example.com"),
        token_manager,
    )

    async def fake_request_json(
        method: str,
        path: str,
        action_name: str,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del method, path, action_name, params, headers, json_body
        return {"status": "success"}

    client._http_client.request_json = fake_request_json  # type: ignore[method-assign]

    with pytest.raises(AppError):
        await client.get_testcase(123)

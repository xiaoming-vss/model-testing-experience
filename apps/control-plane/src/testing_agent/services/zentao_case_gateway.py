"""Explicit testcase reads/writes. Identity choices belong to the durable workflow."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.zentao_mcp import ZentaoMcpConnection, deleted, normalize_list


def remote_id(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("id")
    if (
        isinstance(value, bool)
        or not str(value).isascii()
        or not str(value).isdigit()
        or len(str(value)) > 10
        or not 0 < int(value) <= 2_147_483_647
    ):
        raise AppError(502, "禅道用例编号或归属格式异常", 502)
    return int(value)


class ZentaoCaseGateway:
    """One request-scoped MCP session; complete execution catalogs are reused across suites."""

    def __init__(self, client: McpClient) -> None:
        self.client = client
        self.catalogs: dict[int, dict[int, dict[str, Any]]] = {}
        self.details: dict[int, dict[str, Any]] = {}

    async def catalog(self, execution: int) -> dict[int, dict[str, Any]]:
        if execution in self.catalogs:
            return self.catalogs[execution]
        result: dict[int, dict[str, Any]] = {}
        seen: set[int] = set()
        for page in range(1, 101):
            data = await self.client.call(
                "get_executions_executionID_testcases",
                {
                    "executionID": execution,
                    "browseType": "all",
                    "orderBy": "id_asc",
                    "pageID": page,
                    "recPerPage": 100,
                },
            )
            raw = data.get("testcases")
            if isinstance(raw, dict):
                raw = list(raw.values())
            if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
                raise AppError(502, "禅道用例列表格式异常", 502)
            batch, total = normalize_list(
                {
                    **data,
                    "testcases": [
                        {**item, "id": item.get("case") or item.get("caseID") or item.get("id")}
                        for item in raw
                    ],
                },
                "testcases",
            )
            for item in batch:
                identifier = remote_id(item["id"])
                if identifier in seen:
                    raise AppError(502, "禅道用例分页重复，未发出写入", 502)
                seen.add(identifier)
                if not item["deleted"]:
                    result[identifier] = item
            if total is not None and len(seen) >= total:
                break
            if total is None and len(batch) < 100:
                break
            if not batch:
                raise AppError(502, "禅道用例分页不完整，未发出写入", 502)
        else:
            raise AppError(502, "禅道用例超过查询上限，未发出写入", 502)
        # Most list responses already carry the title. Fetch details only when missing.
        for identifier, item in result.items():
            if not isinstance(item.get("title"), str):
                result[identifier] = await self.detail(identifier)
        self.catalogs[execution] = result
        return result

    async def detail(self, identifier: int, *, fresh: bool = False) -> dict[str, Any]:
        if not fresh and identifier in self.details:
            return self.details[identifier]
        detail = (await self.client.call("get_testcases_caseID", {"caseID": identifier})).get(
            "testcase"
        )
        if not isinstance(detail, dict) or remote_id(detail.get("id")) != identifier:
            raise AppError(502, "禅道用例详情格式异常", 502)
        if deleted(detail.get("deleted")):
            raise AppError(409, "远端用例已删除，请核对映射", 409)
        self.details[identifier] = detail
        return detail

    async def verify_target(self, identifier: int, target: dict[str, int]) -> dict[str, Any]:
        if identifier not in await self.catalog(target["execution"]):
            raise AppError(409, "所选远端用例不属于目标执行", 409)
        detail = await self.detail(identifier, fresh=True)
        if (
            remote_id(detail.get("product")) != target["productID"]
            or remote_id(detail.get("story")) != target["story"]
        ):
            raise AppError(409, "所选远端用例不属于目标产品或需求", 409)
        return detail

    async def write(
        self,
        payload: dict[str, Any],
        target: dict[str, int],
        identifier: int | None,
    ) -> int:
        """Exactly one call, only after the coordinator commits a fresh write permit."""
        body = {**payload, "type": "feature", "stepType": ["step"] * len(payload["steps"])}
        args: dict[str, Any]
        if identifier is None:
            body.update({key: target[key] for key in ("productID", "project", "execution")})
            name, args = "post_testcases", {"payload": body}
        else:
            name, args = "put_testcases_testcasID", {"testcasID": identifier, "payload": body}
        result = await self.client.call(name, args, write=True)
        if result.get("status") != "success":
            raise McpCallError("禅道未明确返回成功", uncertain=True)
        try:
            received = remote_id(result.get("id", identifier))
        except AppError:
            raise McpCallError("禅道未返回有效用例编号", uncertain=True) from None
        if identifier is not None and received != identifier:
            raise McpCallError("禅道回执用例编号与操作目标不一致", uncertain=True)
        self.details.pop(received, None)
        if target["execution"] in self.catalogs:
            self.catalogs[target["execution"]][received] = {"id": str(received), **payload}
        return received


def content_matches(detail: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Read-only reconciliation requires every written field, never merely a matching title."""
    for field in ("title", "precondition"):
        if str(detail.get(field) or "").strip() != str(payload.get(field) or "").strip():
            return False
    for field in ("pri", "module", "story"):
        value = detail.get(field)
        if isinstance(value, dict):
            value = value.get("id")
        if str(value if value is not None else "") != str(payload.get(field)):
            return False
    steps = detail.get("steps")
    if isinstance(steps, dict):
        steps = list(steps.values())
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        return False
    actual = [
        (str(step.get("desc") or "").strip(), str(step.get("expect") or "").strip())
        for step in steps
    ]
    expected = [
        (str(action).strip(), str(expect).strip())
        for action, expect in zip(payload["steps"], payload["expects"], strict=True)
    ]
    return actual == expected


@asynccontextmanager
async def open_case_gateway(connection: ZentaoMcpConnection) -> AsyncIterator[ZentaoCaseGateway]:
    async with McpClient(connection.endpoint, connection.token) as client:
        yield ZentaoCaseGateway(client)

"""Deterministic testcase push over MCP; no AI or legacy connector involved."""

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.zentao_mcp import ZentaoMcpResources, deleted, normalize_list


class ZentaoMcpCases:
    async def validate_target(self, connection, project, execution, story, product):
        resources = ZentaoMcpResources()
        remote = await resources.get_project(connection, str(project))
        executions = await resources.read(connection, "executions", str(project))
        stories = await resources.read(connection, "stories", str(execution))
        if (
            remote.deleted
            or not any(
                item["id"] == str(execution) and not item["deleted"] for item in executions["items"]
            )
            or not any(
                item["id"] == str(story) and not item["deleted"] for item in stories["items"]
            )
        ):
            raise AppError(400, "禅道绑定已失效或远端层级不匹配", 400)
        try:
            async with McpClient(connection.endpoint, connection.token) as client:
                data = await client.call("get_stories_storyID", {"storyID": story})
            detail = data.get("story", {})
            if not isinstance(detail, dict):
                raise AppError(502, "禅道需求详情格式异常", 502)
            if str(detail.get("id")) != str(story) or deleted(detail.get("deleted")):
                raise AppError(400, "禅道需求不存在或已删除", 400)
            if str(detail.get("product")) != str(product):
                raise AppError(400, "所选产品与绑定的禅道需求所属产品不一致", 400)
        except McpCallError as exc:
            raise AppError(502, str(exc), 502) from exc

    async def _existing(self, client, execution):
        ids, seen = [], set()
        for page in range(1, 101):
            data = await client.call(
                "get_executions_executionID_testcases",
                {
                    "executionID": execution,
                    "browseType": "all",
                    "orderBy": "id_asc",
                    "pageID": page,
                    "recPerPage": 100,
                },
            )
            # Execution testcase rows may identify the association by id, testcase by case.
            raw = data.get("testcases")
            if isinstance(raw, dict):
                raw = list(raw.values())
            if not isinstance(raw, list) or any(not isinstance(i, dict) for i in raw):
                raise McpCallError("禅道用例列表格式异常")
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
                if item["id"] in seen:
                    raise McpCallError("禅道用例分页重复，已停止推送")
                seen.add(item["id"])
                if not item["deleted"]:
                    ids.append(item["id"])
            if (total is not None and len(seen) >= total) or (total is None and len(batch) < 100):
                break
            if not batch:
                raise McpCallError("禅道用例分页不完整，已停止推送")
        else:
            raise McpCallError("禅道用例超过查询上限，已停止推送")
        titles: dict[str, int] = {}
        for identifier in ids:
            detail = (await client.call("get_testcases_caseID", {"caseID": identifier})).get(
                "testcase"
            )
            if not isinstance(detail, dict) or str(detail.get("id")) != identifier:
                raise McpCallError("禅道用例详情格式异常")
            if not deleted(detail.get("deleted")):
                title = str(detail.get("title") or "").strip()
                if title:
                    titles.setdefault(title, int(identifier))
        return titles

    async def create_test_cases(self, connection, body):
        items = []
        async with McpClient(connection.endpoint, connection.token) as client:
            titles = await self._existing(client, body["execution"])
            stopped = False
            for case in body["cases"]:
                if stopped:
                    items.append(
                        {"id": 0, "status": "skipped", "errorMessage": "前序用例未成功，未继续推送"}
                    )
                    continue
                matched = titles.get(case["title"].strip())
                payload = {**case, "type": "feature", "stepType": ["step"] * len(case["steps"])}
                if matched is None:
                    payload.update(
                        {key: body[key] for key in ("productID", "project", "execution")}
                    )
                    name, args = "post_testcases", {"payload": payload}
                else:
                    name, args = (
                        "put_testcases_testcasID",
                        {"testcasID": matched, "payload": payload},
                    )
                try:
                    data = await client.call(name, args, write=True)
                    if data.get("status") != "success":
                        raise McpCallError("禅道未明确返回成功", uncertain=True)
                    identifier = data.get("id", matched)
                    if (
                        isinstance(identifier, bool)
                        or not str(identifier).isdigit()
                        or int(identifier) <= 0
                    ):
                        raise McpCallError("禅道未返回有效用例编号", uncertain=True)
                    titles[case["title"].strip()] = int(identifier)
                    items.append({"id": int(identifier), "status": "success"})
                except McpCallError as exc:
                    stopped = True
                    items.append(
                        {
                            "id": matched or 0,
                            "status": "uncertain" if exc.uncertain else "failed",
                            "errorMessage": str(exc)
                            + ("；请先在禅道核对，勿直接重试" if exc.uncertain else ""),
                        }
                    )
        return {"items": items, "total": len(items)}

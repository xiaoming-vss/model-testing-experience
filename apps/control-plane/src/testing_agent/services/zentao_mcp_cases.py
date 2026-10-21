"""Deterministic testcase push over MCP; no AI or legacy connector involved."""

from testing_agent.core.errors import AppError
from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.zentao_mcp import ZentaoMcpResources, deleted


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

from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.zentao_mcp import normalize_list, read_all_pages

PAGE_LIMIT = 100
PAGE_COUNT_LIMIT = 100


async def fetch_detail(client: McpClient, remote_bug_id: int) -> dict:
    data = await client.call("get_bugs_bugID", {"bugID": remote_bug_id})
    bug = data.get("bug", {})
    if not isinstance(bug, dict):
        raise McpCallError("禅道 Bug 详情格式异常")
    return bug


async def paged_remote_bugs(client: McpClient, tool: str, arguments: dict) -> list[dict]:
    async def fetch(page: int) -> dict:
        return await client.call(
            tool,
            {
                **arguments,
                "browseType": "all",
                "orderBy": "id_asc",
                "pageID": page,
                "recPerPage": PAGE_LIMIT,
            },
        )

    return await read_all_pages(
        fetch,
        lambda data: normalize_list(data, "bugs"),
        page_size=PAGE_LIMIT,
        duplicate_message="禅道 Bug 分页重复，已停止读取",
        incomplete_message="禅道 Bug 分页数据不完整",
        limit_message="禅道 Bug 超过查询上限，请缩小筛选范围",
        error=McpCallError,
    )


def optional_remote_id(value: object) -> int:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            return 0
        result = int(str(value).strip())
    except ValueError:
        return 0
    return result if result > 0 else 0

from testing_agent.services.mcp_client import McpCallError, McpClient
from testing_agent.services.zentao_mcp import normalize_list

PAGE_LIMIT = 100
PAGE_COUNT_LIMIT = 100


async def fetch_detail(client: McpClient, remote_bug_id: int) -> dict:
    data = await client.call("get_bugs_bugID", {"bugID": remote_bug_id})
    bug = data.get("bug", {})
    if not isinstance(bug, dict):
        raise McpCallError("禅道 Bug 详情格式异常")
    return bug


async def paged_remote_bugs(client: McpClient, tool: str, arguments: dict) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for page in range(1, PAGE_COUNT_LIMIT + 1):
        data = await client.call(
            tool,
            {
                **arguments,
                "browseType": "all",
                "orderBy": "id_asc",
                "pageID": page,
                "recPerPage": PAGE_LIMIT,
            },
        )
        batch, total = normalize_list(data, "bugs")
        if any(item["id"] in seen for item in batch):
            raise McpCallError("禅道 Bug 分页重复，已停止读取")
        seen.update(item["id"] for item in batch)
        items.extend(batch)
        complete = total is not None and len(items) >= total
        if complete or (total is None and len(batch) < PAGE_LIMIT):
            return items
        if not batch:
            raise McpCallError("禅道 Bug 分页数据不完整")
    raise McpCallError("禅道 Bug 超过查询上限，请缩小筛选范围")


def optional_remote_id(value: object) -> int:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == "":
            return 0
        result = int(str(value).strip())
    except ValueError:
        return 0
    return result if result > 0 else 0

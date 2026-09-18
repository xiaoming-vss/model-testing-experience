from app.clients.zentao.bug_client import ZentaoBugClient
from app.schemas.zentao.bug import BugImportData
from app.schemas.zentao.imports import ImportListData, ImportListQuery, extract_total


class ZentaoBugService:
    def __init__(self, bug_client: ZentaoBugClient) -> None:
        self._bug_client = bug_client

    async def list_execution_bugs(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[BugImportData]:
        payload = await self._bug_client.list_execution_bugs(
            execution_id,
            params=query.to_zentao_params(),
        )
        bugs = [
            BugImportData.from_upstream(item)
            for item in payload.get("bugs", [])
            if isinstance(item, dict)
        ]
        return ImportListData(items=bugs, total=extract_total(payload, len(bugs)))

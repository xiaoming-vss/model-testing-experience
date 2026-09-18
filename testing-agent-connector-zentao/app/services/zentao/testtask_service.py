from app.clients.zentao.testtask_client import ZentaoTestTaskClient
from app.schemas.zentao.imports import (
    ImportListData,
    ImportListQuery,
    TestTaskImportData,
    extract_total,
)


class ZentaoTestTaskService:
    def __init__(self, testtask_client: ZentaoTestTaskClient) -> None:
        self._testtask_client = testtask_client

    async def list_testtasks(
        self,
        execution_id: int,
        query: ImportListQuery,
    ) -> ImportListData[TestTaskImportData]:
        payload = await self._testtask_client.list_testtasks(
            execution_id,
            params=query.to_zentao_params(),
        )
        testtasks = [
            TestTaskImportData.from_upstream(item, fallback_execution_id=execution_id)
            for item in payload.get("testtasks", [])
            if isinstance(item, dict)
        ]
        return ImportListData(items=testtasks, total=extract_total(payload, len(testtasks)))

    async def get_testtask(self, testtask_id: int) -> TestTaskImportData:
        payload = await self._testtask_client.get_testtask(testtask_id)
        return TestTaskImportData.from_upstream(payload["testtask"])

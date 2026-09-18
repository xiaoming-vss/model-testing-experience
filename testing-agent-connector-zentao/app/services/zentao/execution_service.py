from app.clients.zentao.execution_client import ZentaoExecutionClient
from app.schemas.zentao.imports import (
    ExecutionImportData,
    ImportListData,
    ImportListQuery,
    StoryImportData,
    extract_total,
)


class ZentaoExecutionService:
    def __init__(self, execution_client: ZentaoExecutionClient) -> None:
        self._execution_client = execution_client

    async def list_executions(
        self,
        project_id: int,
        query: ImportListQuery,
    ) -> ImportListData[ExecutionImportData]:
        payload = await self._execution_client.list_executions(
            project_id=project_id,
            params=query.to_zentao_params(),
        )
        executions = [
            ExecutionImportData.from_upstream(item, fallback_project_id=project_id)
            for item in payload.get("executions", [])
            if isinstance(item, dict)
        ]
        return ImportListData(items=executions, total=extract_total(payload, len(executions)))

    async def get_execution(self, execution_id: int) -> ExecutionImportData:
        payload = await self._execution_client.get_execution(execution_id)
        return ExecutionImportData.from_upstream(payload["execution"])

    async def list_execution_stories(
        self,
        execution_id: int,
    ) -> ImportListData[StoryImportData]:
        payload = await self._execution_client.list_execution_stories(execution_id)
        stories = [
            StoryImportData.from_upstream(item)
            for item in payload.get("stories", [])
            if isinstance(item, dict)
        ]
        return ImportListData(items=stories, total=extract_total(payload, len(stories)))

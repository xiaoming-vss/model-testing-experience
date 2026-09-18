from app.clients.zentao.project_client import ZentaoProjectClient
from app.schemas.zentao.imports import (
    ImportListData,
    ImportListQuery,
    ProjectImportData,
    extract_total,
)


class ZentaoProjectService:
    def __init__(
        self,
        project_client: ZentaoProjectClient,
    ) -> None:
        self._project_client = project_client

    async def list_projects(self, query: ImportListQuery) -> ImportListData[ProjectImportData]:
        payload = await self._project_client.list_projects(params=query.to_zentao_params())
        projects = [
            ProjectImportData.from_upstream(item)
            for item in payload.get("projects", [])
            if isinstance(item, dict)
        ]
        return ImportListData(items=projects, total=extract_total(payload, len(projects)))

    async def get_project(self, project_id: int) -> ProjectImportData:
        payload = await self._project_client.get_project(project_id)
        return ProjectImportData.from_upstream(payload["project"])

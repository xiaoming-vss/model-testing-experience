from typing import Any

from app.clients.zentao.base import AuthenticatedZentaoClient


class ZentaoProjectClient(AuthenticatedZentaoClient):
    async def list_projects(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path="/projects",
            action_name="Zentao project query",
            params=params,
        )
        return self.ensure_success_payload(payload)

    async def get_project(self, project_id: int) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/projects/{project_id}",
            action_name="Zentao project detail query",
        )
        return self.ensure_success_payload(
            payload,
            invalid_message=f"Zentao returned an invalid project payload: {payload}",
            required_keys=("project",),
        )

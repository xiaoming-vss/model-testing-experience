from typing import Any

from app.clients.zentao.base import AuthenticatedZentaoClient


class ZentaoExecutionClient(AuthenticatedZentaoClient):
    async def list_executions(
        self,
        project_id: int,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/projects/{project_id}/executions",
            action_name="Zentao execution query",
            params=params,
        )
        return self.ensure_success_payload(payload)

    async def get_execution(self, execution_id: int) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/executions/{execution_id}",
            action_name="Zentao execution detail query",
        )
        return self.ensure_success_payload(
            payload,
            invalid_message=f"Zentao returned an invalid execution payload: {payload}",
            required_keys=("execution",),
        )

    async def list_execution_stories(self, execution_id: int) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/executions/{execution_id}/stories",
            action_name="Zentao execution story query",
        )
        return self.ensure_success_payload(payload)

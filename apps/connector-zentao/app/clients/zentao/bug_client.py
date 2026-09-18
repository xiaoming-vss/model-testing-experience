from typing import Any

from app.clients.zentao.base import AuthenticatedZentaoClient


class ZentaoBugClient(AuthenticatedZentaoClient):
    async def list_execution_bugs(
        self,
        execution_id: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/executions/{execution_id}/bugs",
            action_name="Zentao execution bug query",
            params=params,
        )
        return self.ensure_success_payload(payload)

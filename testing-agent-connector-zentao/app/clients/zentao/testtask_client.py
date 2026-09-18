from typing import Any

from app.clients.zentao.base import AuthenticatedZentaoClient


class ZentaoTestTaskClient(AuthenticatedZentaoClient):
    async def list_testtasks(
        self,
        execution_id: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/executions/{execution_id}/testtasks",
            action_name="Zentao test task query",
            params=params,
        )
        return self.ensure_success_payload(payload)

    async def get_testtask(self, testtask_id: int) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/testtasks/{testtask_id}",
            action_name="Zentao test task detail query",
        )
        return self.ensure_success_payload(
            payload,
            invalid_message=f"Zentao returned an invalid test task payload: {payload}",
            required_keys=("testtask",),
        )

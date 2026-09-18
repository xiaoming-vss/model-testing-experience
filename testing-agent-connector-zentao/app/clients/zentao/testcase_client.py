from typing import Any

from app.clients.zentao.base import AuthenticatedZentaoClient


class ZentaoTestCaseClient(AuthenticatedZentaoClient):
    async def create_testcase(self, payload: dict[str, Any]) -> dict[str, Any]:
        response_payload = await self.request_json_with_token(
            method="POST",
            path="/testcases",
            action_name="Zentao testcase create",
            json_body=payload,
        )
        return self.ensure_success_payload(
            response_payload,
            invalid_message=(
                f"Zentao returned an invalid testcase create payload: {response_payload}"
            ),
            required_keys=("id",),
        )

    async def update_testcase(
        self,
        case_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response_payload = await self.request_json_with_token(
            method="PUT",
            path=f"/testcases/{case_id}",
            action_name="Zentao testcase update",
            json_body=payload,
        )
        return self.ensure_success_payload(
            response_payload,
            invalid_message=(
                f"Zentao returned an invalid testcase update payload: {response_payload}"
            ),
        )

    async def list_execution_testcases(
        self,
        execution_id: int,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/executions/{execution_id}/testcases",
            action_name="Zentao execution testcase query",
            params=params,
        )
        return self.ensure_success_payload(payload)

    async def get_testcase(self, case_id: int) -> dict[str, Any]:
        payload = await self.request_json_with_token(
            method="GET",
            path=f"/testcases/{case_id}",
            action_name="Zentao testcase detail query",
        )
        return self.ensure_success_payload(
            payload,
            invalid_message=f"Zentao returned an invalid testcase payload: {payload}",
            required_keys=("testcase",),
        )

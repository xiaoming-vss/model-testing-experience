"""Recording workflow adapter for exporter scope/payload tests; journal has real DB tests."""

from contextlib import asynccontextmanager

from testing_agent.core.errors import ErrZentaoRemoteResourceUnavailable, dynamic_error
from testing_agent.services.function_case_export import FunctionCaseExporter


class RecordingFlow:
    def __init__(self, client):
        self.client = client

    async def frozen_selection(self, actor, request_id, fingerprint):
        return None

    async def admit(self, actor, scope, request_id, fingerprint, manifest):
        return manifest

    async def push_one(self, actor, scope, gateway, *, case_id, payload, **kwargs):
        try:
            response = await self.client.create_test_cases(
                scope.connection,
                {
                    "productID": scope.target["productID"],
                    "project": scope.target["project"],
                    "execution": scope.target["execution"],
                    "cases": [payload],
                },
            )
        except RuntimeError as exc:
            raise dynamic_error(ErrZentaoRemoteResourceUnavailable, str(exc)) from exc
        item = response["items"][0]
        return {
            "caseId": case_id,
            "remoteCaseId": item["id"],
            "status": item["status"],
            **({"errorMessage": item["errorMessage"]} if item.get("errorMessage") else {}),
        }


@asynccontextmanager
async def gateway(connection):
    yield None


def exporter(
    repository, integration_connection_service=None, zentao_resource_client=None, **kwargs
):
    return FunctionCaseExporter(
        repository,
        integration_connection_service,
        zentao_resource_client,
        push_flow=RecordingFlow(zentao_resource_client),
        gateway_factory=gateway,
        **kwargs,
    )

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from testing_agent.api.deps import verify_integration_worker_token, verify_worker_token
from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import AppError


def test_legacy_config_remains_disabled_and_empty_pilot_does_not_select_all():
    assert not Settings.from_mapping({}).integration_execution.uses_worker("p")
    settings = Settings.from_mapping(
        {
            "security": {"worker": {"key": "old"}, "integration_worker": {"key": "dedicated"}},
            "integration_execution": {"enabled": True, "runtime_generation": "generation"},
        }
    )
    assert not settings.integration_execution.uses_worker("p")


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": "false"},
        {"claim_enabled": 1},
        {"lease_seconds": True},
        {"lease_seconds": 9},
        {"lease_seconds": 601},
        {"project_ids": "p"},
        {"project_ids": [1]},
        {"enabled": True},
        {"succeeded_retention_days": 0},
        {"failed_retention_days": True},
        {"maintenance_batch_size": 1001},
        {"worker_presence_ttl_seconds": True},
        {"worker_presence_ttl_seconds": 9},
        {"worker_presence_ttl_seconds": 3601},
    ],
)
def test_invalid_execution_configuration_fails_startup(overrides):
    with pytest.raises(ValueError):
        Settings.from_mapping({"integration_execution": overrides})


def test_dedicated_key_and_runtime_are_required_when_enabled():
    with pytest.raises(ValueError, match="must differ"):
        Settings.from_mapping(
            {
                "security": {
                    "worker": {"key": "same"},
                    "integration_worker": {"key": "same"},
                }
            }
        )
    with pytest.raises(ValueError, match="dedicated Worker key"):
        Settings.from_mapping(
            {
                "integration_execution": {
                    "enabled": True,
                    "runtime_generation": "generation",
                }
            }
        )


def test_pilot_and_submit_claim_switches_are_independent():
    settings = Settings.from_mapping(
        {
            "security": {"integration_worker": {"key": "dedicated"}},
            "integration_execution": {
                "enabled": True,
                "runtime_generation": "generation",
                "project_ids": ["pilot"],
                "accept_submissions": False,
                "claim_enabled": True,
            },
        }
    )
    execution = settings.integration_execution
    assert execution.uses_worker("pilot")
    assert not execution.uses_worker("other")
    assert not execution.accept_submissions
    assert execution.claim_enabled


def test_service_tokens_cannot_cross_worker_route_domains():
    settings = Settings.from_mapping(
        {
            "security": {
                "worker": {"key": "old"},
                "integration_worker": {"key": "dedicated"},
            }
        }
    )
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"code": exc.code}, status_code=exc.http_code)

    @app.get("/integration", dependencies=[Depends(verify_integration_worker_token)])
    def integration():
        return {"domain": "integration"}

    @app.get("/existing", dependencies=[Depends(verify_worker_token)])
    def existing():
        return {"domain": "existing"}

    client = TestClient(app)
    assert client.get("/integration", headers={"X-Worker-Token": "old"}).status_code == 401
    assert client.get("/existing", headers={"X-Worker-Token": "dedicated"}).status_code == 401
    assert client.get("/integration", headers={"X-Worker-Token": "dedicated"}).status_code == 200
    assert client.get("/existing", headers={"X-Worker-Token": "old"}).status_code == 200
    assert client.get("/integration").status_code == 401

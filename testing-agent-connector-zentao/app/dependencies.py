from collections.abc import Callable
from dataclasses import replace

from fastapi import Header

from app.clients.zentao.bug_client import ZentaoBugClient
from app.clients.zentao.execution_client import ZentaoExecutionClient
from app.clients.zentao.project_client import ZentaoProjectClient
from app.clients.zentao.testcase_client import ZentaoTestCaseClient
from app.clients.zentao.testtask_client import ZentaoTestTaskClient
from app.clients.zentao.token_manager import ZentaoTokenManager
from app.core.exceptions import new_bad_request
from app.core.zentao_toml import ZentaoTomlConfig, get_zentao_toml_config
from app.services.zentao import (
    ZentaoBugService,
    ZentaoExecutionService,
    ZentaoProjectService,
    ZentaoTestCaseService,
    ZentaoTestTaskService,
)

ProjectServiceFactory = Callable[[str, str], ZentaoProjectService]
ExecutionServiceFactory = Callable[[str, str], ZentaoExecutionService]
BugServiceFactory = Callable[[str, str], ZentaoBugService]
TestTaskServiceFactory = Callable[[str, str], ZentaoTestTaskService]
TestCaseServiceFactory = Callable[[str, str], ZentaoTestCaseService]


def get_zentao_config() -> ZentaoTomlConfig:
    return get_zentao_toml_config()


def get_zentao_request_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization[7:].strip()
        if bearer_token:
            return bearer_token

    raise new_bad_request("Missing Zentao token. Provide it with `Authorization: Bearer <token>`.")


def get_zentao_project_service_factory() -> ProjectServiceFactory:
    return build_zentao_project_service


def get_zentao_execution_service_factory() -> ExecutionServiceFactory:
    return build_zentao_execution_service


def get_zentao_bug_service_factory() -> BugServiceFactory:
    return build_zentao_bug_service


def get_zentao_testtask_service_factory() -> TestTaskServiceFactory:
    return build_zentao_testtask_service


def get_zentao_testcase_service_factory() -> TestCaseServiceFactory:
    return build_zentao_testcase_service


def build_zentao_project_service(base_url: str, request_token: str) -> ZentaoProjectService:
    config = _build_request_config(base_url)
    token_manager = _build_token_manager(config, request_token)
    project_client = ZentaoProjectClient(config, token_manager)
    return ZentaoProjectService(project_client=project_client)


def build_zentao_execution_service(base_url: str, request_token: str) -> ZentaoExecutionService:
    config = _build_request_config(base_url)
    token_manager = _build_token_manager(config, request_token)
    execution_client = ZentaoExecutionClient(config, token_manager)
    return ZentaoExecutionService(execution_client=execution_client)


def build_zentao_bug_service(base_url: str, request_token: str) -> ZentaoBugService:
    config = _build_request_config(base_url)
    token_manager = _build_token_manager(config, request_token)
    bug_client = ZentaoBugClient(config, token_manager)
    return ZentaoBugService(bug_client=bug_client)


def build_zentao_testtask_service(base_url: str, request_token: str) -> ZentaoTestTaskService:
    config = _build_request_config(base_url)
    token_manager = _build_token_manager(config, request_token)
    testtask_client = ZentaoTestTaskClient(config, token_manager)
    return ZentaoTestTaskService(testtask_client=testtask_client)


def build_zentao_testcase_service(base_url: str, request_token: str) -> ZentaoTestCaseService:
    config = _build_request_config(base_url)
    token_manager = _build_token_manager(config, request_token)
    testcase_client = ZentaoTestCaseClient(config, token_manager)
    return ZentaoTestCaseService(testcase_client=testcase_client)


def _build_request_config(base_url: str) -> ZentaoTomlConfig:
    normalized_base_url = base_url.strip()
    if not normalized_base_url:
        raise new_bad_request("Zentao base_url is required.")
    return replace(get_zentao_config(), base_url=normalized_base_url)


def _build_token_manager(
    config: ZentaoTomlConfig,
    request_token: str,
) -> ZentaoTokenManager:
    return ZentaoTokenManager(config, request_token)

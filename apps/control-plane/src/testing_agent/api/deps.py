from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import ErrUnauthorized
from testing_agent.core.security import parse_access_token
from testing_agent.db.session import get_session
from testing_agent.models.user import User
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.api_assert_rule import ApiAssertRuleRepository
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.repositories.api_environment_var import ApiEnvironmentVarRepository
from testing_agent.repositories.api_extract_rule import ApiExtractRuleRepository
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.repositories.function_test_suite import FunctionTestSuiteRepository
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.project_skill_space import ProjectSkillSpaceRepository
from testing_agent.repositories.requirement import RequirementRepository
from testing_agent.repositories.resource_binding import ResourceBindingRepository
from testing_agent.repositories.sprint import SprintRepository
from testing_agent.repositories.sprint_daily_metrics import SprintDailyMetricsRepository
from testing_agent.repositories.test_order import TestOrderRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.repositories.ui_test_case import UiTestCaseRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.repositories.ui_test_suite import UiTestSuiteRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.repositories.worker_task import WorkerTaskRepository
from testing_agent.services.ai_generate_task import AiGenerateTaskService
from testing_agent.services.api_assert_rule import ApiAssertRuleService
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection import ApiCollectionService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.api_environment import ApiEnvironmentService
from testing_agent.services.api_environment_var import ApiEnvironmentVarService
from testing_agent.services.api_extract_rule import ApiExtractRuleService
from testing_agent.services.auth import AuthService
from testing_agent.services.baseline_resolution import BaselineResolutionService
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService
from testing_agent.services.function_test_case import FunctionTestCaseService
from testing_agent.services.function_test_suite import FunctionTestSuiteService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.project import ProjectService
from testing_agent.services.project_skill_space import ProjectSkillSpaceService
from testing_agent.services.requirement import RequirementService
from testing_agent.services.resource_binding import ResourceBindingService
from testing_agent.services.sprint import SprintService
from testing_agent.services.sprint_code_overview import (
    SprintCodeOverviewService,
)
from testing_agent.services.sprint_daily_metrics import SprintDailyMetricsService
from testing_agent.services.test_order import TestOrderService
from testing_agent.services.test_order_entry import TestOrderEntryService
from testing_agent.services.test_order_graph import TestOrderGraphService
from testing_agent.services.ui_test_case import UiTestCaseService
from testing_agent.services.ui_test_case_run import UiTestCaseRunService
from testing_agent.services.ui_test_suite import UiTestSuiteService
from testing_agent.services.worker_task import WorkerTaskService
from testing_agent.services.zentao_resource import ZentaoResourceClient


async def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> str:
    if not authorization:
        raise ErrUnauthorized
    token = authorization.removeprefix("Bearer ").strip()
    user_id = parse_access_token(token)
    if await session.scalar(select(User.user_id).where(User.user_id == user_id)) is None:
        raise ErrUnauthorized
    return user_id


def verify_worker_token(
    x_worker_token: Annotated[str | None, Header(alias="X-Worker-Token")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.worker_key or not x_worker_token or x_worker_token != settings.worker_key:
        raise ErrUnauthorized


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session))


def get_project_service(session: AsyncSession = Depends(get_session)) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def build_project_service(session: AsyncSession) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def get_sprint_service(session: AsyncSession = Depends(get_session)) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def build_sprint_service(session: AsyncSession) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def get_requirement_service(session: AsyncSession = Depends(get_session)) -> RequirementService:
    return RequirementService(RequirementRepository(session), build_sprint_service(session))


def get_api_case_service(session: AsyncSession = Depends(get_session)) -> ApiCaseService:
    return ApiCaseService(ApiCaseRepository(session))


def build_api_case_service(session: AsyncSession) -> ApiCaseService:
    return ApiCaseService(ApiCaseRepository(session))


def get_api_collection_service(
    session: AsyncSession = Depends(get_session),
) -> ApiCollectionService:
    return ApiCollectionService(ApiCollectionRepository(session))


def get_api_collection_run_service(
    session: AsyncSession = Depends(get_session),
) -> ApiCollectionRunService:
    return ApiCollectionRunService(ApiCollectionRunRepository(session))


def get_api_environment_service(
    session: AsyncSession = Depends(get_session),
) -> ApiEnvironmentService:
    return ApiEnvironmentService(ApiEnvironmentRepository(session))


def get_api_environment_var_service(
    session: AsyncSession = Depends(get_session),
) -> ApiEnvironmentVarService:
    return ApiEnvironmentVarService(ApiEnvironmentVarRepository(session))


def get_api_assert_rule_service(
    session: AsyncSession = Depends(get_session),
) -> ApiAssertRuleService:
    return ApiAssertRuleService(
        ApiAssertRuleRepository(session),
        build_api_case_service(session),
    )


def get_api_extract_rule_service(
    session: AsyncSession = Depends(get_session),
) -> ApiExtractRuleService:
    return ApiExtractRuleService(
        ApiExtractRuleRepository(session),
        build_api_case_service(session),
    )


def get_function_test_suite_service(
    session: AsyncSession = Depends(get_session),
) -> FunctionTestSuiteService:
    return FunctionTestSuiteService(FunctionTestSuiteRepository(session))


def get_function_test_case_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FunctionTestCaseService:
    zentao_resource_client = ZentaoResourceClient(settings.zentao_service_base_url)
    return FunctionTestCaseService(
        FunctionTestCaseRepository(session),
        IntegrationConnectionService(
            IntegrationConnectionRepository(session),
            zentao_resource_client,
        ),
        zentao_resource_client,
    )


def get_ui_test_suite_service(
    session: AsyncSession = Depends(get_session),
) -> UiTestSuiteService:
    return UiTestSuiteService(UiTestSuiteRepository(session))


def get_ui_test_case_service(
    session: AsyncSession = Depends(get_session),
) -> UiTestCaseService:
    return UiTestCaseService(UiTestCaseRepository(session))


def get_ui_test_case_run_service(
    session: AsyncSession = Depends(get_session),
) -> UiTestCaseRunService:
    return UiTestCaseRunService(UiTestCaseRunRepository(session))


def get_integration_connection_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IntegrationConnectionService:
    return IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        ZentaoResourceClient(settings.zentao_service_base_url),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def get_resource_binding_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> ResourceBindingService:
    return ResourceBindingService(
        ResourceBindingRepository(session),
        IntegrationConnectionService(
            IntegrationConnectionRepository(session),
            ZentaoResourceClient(settings.zentao_service_base_url),
            credential_cipher=IntegrationCredentialCipher(settings.integration_key),
        ),
        ZentaoResourceClient(settings.zentao_service_base_url),
    )


def get_sprint_code_overview_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintCodeOverviewService:
    zentao_resource_client = ZentaoResourceClient(settings.zentao_service_base_url)
    credential_cipher = IntegrationCredentialCipher(settings.integration_key)
    binding_repository = ResourceBindingRepository(session)
    integration_connection_service = IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        zentao_resource_client,
        credential_cipher=credential_cipher,
    )
    return SprintCodeOverviewService(
        build_sprint_service(session),
        binding_repository,
        BaselineResolutionService(binding_repository, SprintRepository(session)),
        integration_connection_service,
        credential_cipher,
    )


def get_project_skill_space_service(
    session: AsyncSession = Depends(get_session),
) -> ProjectSkillSpaceService:
    return ProjectSkillSpaceService(ProjectSkillSpaceRepository(session))


def get_sprint_daily_metrics_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintDailyMetricsService:
    zentao_resource_client = ZentaoResourceClient(settings.zentao_service_base_url)
    return SprintDailyMetricsService(
        SprintDailyMetricsRepository(session),
        IntegrationConnectionService(
            IntegrationConnectionRepository(session),
            zentao_resource_client,
        ),
        zentao_resource_client,
    )


def get_ai_generate_task_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AiGenerateTaskService:
    zentao_resource_client = ZentaoResourceClient(settings.zentao_service_base_url)
    credential_cipher = IntegrationCredentialCipher(settings.integration_key)
    integration_connection_service = IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        zentao_resource_client,
        credential_cipher=credential_cipher,
    )
    binding_repository = ResourceBindingRepository(session)
    return AiGenerateTaskService(
        AiGenerateTaskRepository(session),
        SprintDailyMetricsService(
            SprintDailyMetricsRepository(session),
            IntegrationConnectionService(
                IntegrationConnectionRepository(session),
                zentao_resource_client,
            ),
            zentao_resource_client,
        ),
        settings.uploads_dir,
        code_risk_analysis_service=CodeRiskAnalysisService(
            AiGenerateTaskRepository(session),
            binding_repository,
            BaselineResolutionService(binding_repository, SprintRepository(session)),
            integration_connection_service,
            credential_cipher,
        ),
    )


def get_worker_task_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WorkerTaskService:
    return WorkerTaskService(
        WorkerTaskRepository(session),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def build_test_order_service(session: AsyncSession) -> TestOrderService:
    return TestOrderService(TestOrderRepository(session), TestOrderEntryRepository(session))


def get_test_order_service(
    session: AsyncSession = Depends(get_session),
) -> TestOrderService:
    return build_test_order_service(session)


def get_test_order_entry_service(
    session: AsyncSession = Depends(get_session),
) -> TestOrderEntryService:
    return TestOrderEntryService(
        TestOrderEntryRepository(session),
        build_test_order_service(session),
    )


def get_test_order_graph_service(
    session: AsyncSession = Depends(get_session),
) -> TestOrderGraphService:
    return TestOrderGraphService(
        AiGenerateTaskRepository(session),
        build_test_order_service(session),
        TestOrderEntryRepository(session),
    )

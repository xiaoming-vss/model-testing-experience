from __future__ import annotations

import logging
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.errors import (
    AppError,
    ErrForbidden,
    ErrUnauthorized,
)
from testing_agent.core.ldap_directory import LdapDirectory
from testing_agent.db.session import get_session
from testing_agent.models.user import User
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.ai_generate_task_source_archive import (
    AiGenerateTaskSourceArchiveRepository,
)
from testing_agent.repositories.api_assert_rule import ApiAssertRuleRepository
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.repositories.api_environment_var import ApiEnvironmentVarRepository
from testing_agent.repositories.api_extract_rule import ApiExtractRuleRepository
from testing_agent.repositories.auth_runtime import AuthRuntimeRepository
from testing_agent.repositories.auth_session import AuthSessionRepository
from testing_agent.repositories.bug import BugRepository
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.repositories.function_test_suite import FunctionTestSuiteRepository
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.login_rate_limit import LoginRateLimitRepository
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
from testing_agent.services.ai_task_commands import GenerationTaskCommands
from testing_agent.services.ai_task_queries import GenerationQueries
from testing_agent.services.ai_task_scope import GenerationAccess
from testing_agent.services.api_assert_rule import ApiAssertRuleService
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection import ApiCollectionService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.api_environment import ApiEnvironmentService
from testing_agent.services.api_environment_var import ApiEnvironmentVarService
from testing_agent.services.api_extract_rule import ApiExtractRuleService
from testing_agent.services.auth import AuthService
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import SessionService
from testing_agent.services.baseline_resolution import BaselineResolutionService
from testing_agent.services.bug import BugService
from testing_agent.services.code_risk_analysis import CodeRiskAnalysisService
from testing_agent.services.function_case_export import FunctionCaseExporter
from testing_agent.services.function_case_import import FunctionCaseImporter
from testing_agent.services.function_test_case import FunctionTestCaseService
from testing_agent.services.function_test_suite import FunctionTestSuiteService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.ldap_login import LdapLoginService
from testing_agent.services.ldap_settings import LdapSettingsService, effective_settings
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
from testing_agent.services.user_admin import UserAdminService
from testing_agent.services.worker_task import WorkerTaskService
from testing_agent.services.zentao_mcp import ZentaoMcpResources
from testing_agent.services.zentao_mcp_cases import ZentaoMcpCases


async def get_access_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization:
        raise ErrUnauthorized()
    return authorization.removeprefix("Bearer ").strip()


async def get_current_user_id(
    request: Request,
    token: str = Depends(get_access_token),
    session: AsyncSession = Depends(get_session),
) -> str:
    return await SessionService(AuthSessionRepository(session), get_settings()).authenticate(
        token, method=request.method, path=request.url.path
    )


async def require_super_admin(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> str:
    is_super_admin = await session.scalar(
        select(User.is_super_admin).where(User.user_id == user_id)
    )
    if not is_super_admin:
        raise ErrForbidden()
    return user_id


def verify_worker_token(
    x_worker_token: Annotated[str | None, Header(alias="X-Worker-Token")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.worker_key or not x_worker_token or x_worker_token != settings.worker_key:
        raise ErrUnauthorized()


def verify_integration_worker_token(
    x_worker_token: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.integration_worker_key
    if (
        not expected
        or not x_worker_token
        or not compare_digest(x_worker_token.encode(), expected.encode())
    ):
        logging.getLogger(__name__).warning("Integration worker authentication rejected status=401")
        raise ErrUnauthorized()


async def get_effective_settings(session: AsyncSession = Depends(get_session)) -> Settings:
    return await effective_settings(AuthRuntimeRepository(session), get_settings())


def get_ldap_settings_service(session: AsyncSession = Depends(get_session)) -> LdapSettingsService:
    return LdapSettingsService(AuthRuntimeRepository(session), get_settings())


async def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    users = UserRepository(session)
    try:
        settings = await effective_settings(AuthRuntimeRepository(session), get_settings())
    except AppError:
        # Keep local super-admin recovery available if stored LDAP credentials cannot decrypt.
        settings = get_settings()
        return AuthService(
            users,
            LoginRateLimitRepository(session),
            settings,
            mode=AuthModeService(AuthRuntimeRepository(session), settings),
        )
    users = UserRepository(session)
    limits = LoginRateLimitRepository(session)
    ldap_login = LdapLoginService(
        users,
        limits,
        AuthModeService(AuthRuntimeRepository(session), settings),
        settings,
        LdapDirectory(settings.ldap),
    )
    return AuthService(users, limits, settings, ldap_login=ldap_login, mode=ldap_login.mode)


async def get_user_admin_service(session: AsyncSession = Depends(get_session)) -> UserAdminService:
    settings = await effective_settings(AuthRuntimeRepository(session), get_settings())
    return UserAdminService(
        UserRepository(session),
        ProjectRepository(session),
        settings,
        mode=AuthModeService(AuthRuntimeRepository(session), settings),
    )


def get_project_service(session: AsyncSession = Depends(get_session)) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def build_project_service(session: AsyncSession) -> ProjectService:
    return ProjectService(ProjectRepository(session))


def get_sprint_service(session: AsyncSession = Depends(get_session)) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def build_sprint_service(session: AsyncSession) -> SprintService:
    return SprintService(SprintRepository(session), build_project_service(session))


def get_requirement_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
) -> RequirementService:
    from testing_agent.services.stored_file import StoredFileService

    return RequirementService(
        RequirementRepository(session),
        build_sprint_service(session),
        StoredFileService(session, settings.s3),
    )


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
) -> FunctionTestCaseService:
    return FunctionTestCaseService(FunctionTestCaseRepository(session))


def get_function_case_importer(
    session: AsyncSession = Depends(get_session),
) -> FunctionCaseImporter:
    return FunctionCaseImporter(FunctionTestCaseRepository(session))


def get_function_case_exporter(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FunctionCaseExporter:
    return FunctionCaseExporter(
        FunctionTestCaseRepository(session),
        IntegrationConnectionService(
            IntegrationConnectionRepository(session),
            credential_cipher=IntegrationCredentialCipher(settings.integration_key),
        ),
        ZentaoMcpCases(),
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
            ZentaoMcpResources(),
            credential_cipher=IntegrationCredentialCipher(settings.integration_key),
        ),
        ZentaoMcpResources(),
    )


def get_sprint_code_overview_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintCodeOverviewService:
    credential_cipher = IntegrationCredentialCipher(settings.integration_key)
    binding_repository = ResourceBindingRepository(session)
    integration_connection_service = IntegrationConnectionService(
        IntegrationConnectionRepository(session),
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
    settings: Settings = Depends(get_settings),
) -> ProjectSkillSpaceService:
    return ProjectSkillSpaceService(
        ProjectSkillSpaceRepository(session), get_file_service(session, settings)
    )


def get_sprint_daily_metrics_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SprintDailyMetricsService:
    return SprintDailyMetricsService(SprintDailyMetricsRepository(session))


def get_generation_access(
    session: AsyncSession = Depends(get_session),
) -> GenerationAccess:
    return GenerationAccess(AiGenerateTaskRepository(session))


def get_generation_queries(
    access: GenerationAccess = Depends(get_generation_access),
) -> GenerationQueries:
    return GenerationQueries(
        access.repository,
        AiGenerateTaskSourceArchiveRepository(access.repository.session),
        access,
    )


def get_generation_task_commands(
    access: GenerationAccess = Depends(get_generation_access),
) -> GenerationTaskCommands:
    return GenerationTaskCommands(
        access.repository,
        AiGenerateTaskSourceArchiveRepository(access.repository.session),
        access,
    )


def get_ai_generate_task_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AiGenerateTaskService:
    credential_cipher = IntegrationCredentialCipher(settings.integration_key)
    integration_connection_service = IntegrationConnectionService(
        IntegrationConnectionRepository(session),
        credential_cipher=credential_cipher,
    )
    binding_repository = ResourceBindingRepository(session)
    return AiGenerateTaskService(
        AiGenerateTaskRepository(session),
        SprintDailyMetricsService(SprintDailyMetricsRepository(session)),
        files=get_file_service(session, settings),
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


def build_bug_service(session: AsyncSession, settings) -> BugService:
    from testing_agent.services.stored_file import StoredFileService

    return BugService(BugRepository(session), files=StoredFileService(session, settings.s3))


def get_bug_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BugService:
    return build_bug_service(session, settings)


def build_integration_bug_service(session: AsyncSession, settings: Settings):
    from testing_agent.repositories.integration_job import IntegrationJobRepository
    from testing_agent.services.bug_zentao_push import BugZentaoPushService
    from testing_agent.services.integration_authorization import IntegrationAuthorization
    from testing_agent.services.integration_bug import IntegrationBugService

    pushes = BugZentaoPushService(
        build_bug_service(session, settings), get_integration_connection_service(session, settings)
    )
    return IntegrationBugService(
        IntegrationJobRepository(session),
        pushes,
        IntegrationAuthorization(session, IntegrationCredentialCipher(settings.integration_key)),
        settings,
    )


def get_integration_bug_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return build_integration_bug_service(session, settings)


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


def get_file_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
):
    from testing_agent.services.stored_file import StoredFileService

    return StoredFileService(session, settings.s3)

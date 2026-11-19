from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session
from testing_agent.repositories.ai_generate_task import AiGenerateTaskRepository
from testing_agent.repositories.api_assert_rule import ApiAssertRuleRepository
from testing_agent.repositories.api_case import ApiCaseRepository
from testing_agent.repositories.api_collection import ApiCollectionRepository
from testing_agent.repositories.api_collection_run import ApiCollectionRunRepository
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.repositories.api_environment_var import ApiEnvironmentVarRepository
from testing_agent.repositories.api_extract_rule import ApiExtractRuleRepository
from testing_agent.repositories.api_interface import ApiInterfaceRepository
from testing_agent.repositories.function_test_case import FunctionTestCaseRepository
from testing_agent.repositories.function_test_suite import FunctionTestSuiteRepository
from testing_agent.repositories.integration_connection import IntegrationConnectionRepository
from testing_agent.repositories.monitoring_connection import MonitoringConnectionRepository
from testing_agent.repositories.software_repository import SoftwareRepositoryRepository
from testing_agent.repositories.test_order import TestOrderRepository
from testing_agent.repositories.test_order_entry import TestOrderEntryRepository
from testing_agent.repositories.ui_test_case import UiTestCaseRepository
from testing_agent.repositories.ui_test_case_run import UiTestCaseRunRepository
from testing_agent.repositories.ui_test_suite import UiTestSuiteRepository
from testing_agent.services.api_assert_rule import ApiAssertRuleService
from testing_agent.services.api_case import ApiCaseService
from testing_agent.services.api_collection import ApiCollectionService
from testing_agent.services.api_collection_run import ApiCollectionRunService
from testing_agent.services.api_environment import ApiEnvironmentService
from testing_agent.services.api_environment_var import ApiEnvironmentVarService
from testing_agent.services.api_extract_rule import ApiExtractRuleService
from testing_agent.services.api_interface import ApiInterfaceService
from testing_agent.services.api_interface_import import ApiInterfaceImportService
from testing_agent.services.function_case_export import FunctionCaseExporter
from testing_agent.services.function_case_import import FunctionCaseImporter
from testing_agent.services.function_test_case import FunctionTestCaseService
from testing_agent.services.function_test_suite import FunctionTestSuiteService
from testing_agent.services.integration_connection import IntegrationConnectionService
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.monitoring_connection import MonitoringConnectionService
from testing_agent.services.test_order import TestOrderService
from testing_agent.services.test_order_case_visualization import (
    TestOrderCaseVisualizationService,
)
from testing_agent.services.test_order_entry import TestOrderEntryService
from testing_agent.services.test_order_graph import TestOrderGraphService
from testing_agent.services.ui_run_variables import UiRunVariablesService
from testing_agent.services.ui_test_case import UiTestCaseService
from testing_agent.services.ui_test_case_run import UiTestCaseRunService
from testing_agent.services.ui_test_suite import UiTestSuiteService
from testing_agent.services.zentao_mcp_cases import ZentaoMcpCases


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
        settings=settings,
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


def get_ui_run_variables_service(
    session: AsyncSession = Depends(get_session),
) -> UiRunVariablesService:
    return UiRunVariablesService(session)


def get_monitoring_connection_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MonitoringConnectionService:
    return MonitoringConnectionService(
        MonitoringConnectionRepository(session),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def get_api_interface_service(
    session: AsyncSession = Depends(get_session),
) -> ApiInterfaceService:
    return ApiInterfaceService(
        ApiInterfaceRepository(session),
        SoftwareRepositoryRepository(session),
    )


def get_api_interface_import_service(
    session: AsyncSession = Depends(get_session),
) -> ApiInterfaceImportService:
    return ApiInterfaceImportService(
        ApiInterfaceRepository(session),
        SoftwareRepositoryRepository(session),
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


def get_case_visualization_service(
    session: AsyncSession = Depends(get_session),
) -> TestOrderCaseVisualizationService:
    from testing_agent.repositories.case_visualization import CaseVisualizationRepository
    from testing_agent.services.test_order_case_visualization import (
        TestOrderCaseVisualizationService,
    )

    return TestOrderCaseVisualizationService(
        CaseVisualizationRepository(session),
        build_test_order_service(session),
    )

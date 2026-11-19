from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session
from testing_agent.repositories.api_environment import ApiEnvironmentRepository
from testing_agent.repositories.monitoring_connection import MonitoringConnectionRepository
from testing_agent.repositories.perf_case import PerfCaseRepository
from testing_agent.repositories.perf_run import PerfRunRepository
from testing_agent.repositories.perf_suite import PerfSuiteRepository
from testing_agent.repositories.perf_suite_run import PerfSuiteRunRepository
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.monitoring_connection import MonitoringConnectionService
from testing_agent.services.perf_case import PerfCaseService
from testing_agent.services.perf_run import PerfRunService
from testing_agent.services.perf_suite import PerfSuiteService
from testing_agent.services.perf_suite_run import PerfSuiteRunService
from testing_agent.services.perf_worker import PerfWorkerService


def get_perf_worker_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PerfWorkerService:
    from testing_agent.services.stored_file import StoredFileService

    return PerfWorkerService(
        session,
        files=StoredFileService(session, settings.s3),
        credential_cipher=IntegrationCredentialCipher(settings.integration_key),
    )


def get_perf_case_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PerfCaseService:
    from testing_agent.services.stored_file import StoredFileService

    return PerfCaseService(
        PerfCaseRepository(session),
        files=StoredFileService(session, settings.s3),
    )


def get_perf_run_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PerfRunService:
    from testing_agent.services.stored_file import StoredFileService

    cipher = IntegrationCredentialCipher(settings.integration_key)
    monitoring_service = MonitoringConnectionService(
        MonitoringConnectionRepository(session),
        credential_cipher=cipher,
    )
    return PerfRunService(
        PerfRunRepository(session),
        cases=PerfCaseRepository(session),
        environments=ApiEnvironmentRepository(session),
        monitoring=MonitoringConnectionRepository(session),
        monitoring_service=monitoring_service,
        files=StoredFileService(session, settings.s3),
        credential_cipher=cipher,
    )


def get_perf_suite_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PerfSuiteService:
    from testing_agent.services.stored_file import StoredFileService

    return PerfSuiteService(
        PerfSuiteRepository(session),
        cases=PerfCaseRepository(session),
        runs=PerfSuiteRunRepository(session),
        files=StoredFileService(session, settings.s3),
    )


def get_perf_suite_run_service(
    session: AsyncSession = Depends(get_session),
    perf_runs: PerfRunService = Depends(get_perf_run_service),
) -> PerfSuiteRunService:
    return PerfSuiteRunService(
        PerfSuiteRunRepository(session),
        suites=PerfSuiteRepository(session),
        cases=PerfCaseRepository(session),
        runs=PerfRunRepository(session),
        perf_runs=perf_runs,
    )

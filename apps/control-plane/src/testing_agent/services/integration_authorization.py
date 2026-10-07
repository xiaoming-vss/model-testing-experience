"""Local authorization only. Worker access is scoped to the job actor and bound service."""

from dataclasses import dataclass, field

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.errors import ErrForbidden, ErrNotFound
from testing_agent.domain.integration_execution import digest
from testing_agent.models.bug import Bug
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.integration_job import IntegrationJob
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.shared_service import ServiceAuthorization, SharedService
from testing_agent.models.user import User
from testing_agent.services.integration_credentials import IntegrationCredentialCipher
from testing_agent.services.project_access import allowed_actions


@dataclass(frozen=True, slots=True)
class IntegrationAuthority:
    service: SharedService = field(repr=False)
    connection: IntegrationConnection = field(repr=False)
    access_revision: str


@dataclass(frozen=True, slots=True)
class IntegrationAccess:
    endpoint: str
    token: SecretStr = field(repr=False)
    access_revision: str


@dataclass(frozen=True, slots=True)
class IntegrationSubject:
    project_id: str
    bug_id: str
    actor_user_id: str
    service_id: str
    connection_id: str


class IntegrationAuthorization:
    def __init__(self, session: AsyncSession, cipher: IntegrationCredentialCipher):
        self.session = session
        self.cipher = cipher

    async def authority(self, job: IntegrationJob | IntegrationSubject) -> IntegrationAuthority:
        project = await self.session.scalar(
            select(Project)
            .where(Project.project_id == job.project_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None:
            raise ErrNotFound()
        role = (
            "owner"
            if project.user_id == job.actor_user_id
            else await self.session.scalar(
                select(ProjectMember.role)
                .where(
                    ProjectMember.project_id == job.project_id,
                    ProjectMember.user_id == job.actor_user_id,
                )
                .with_for_update()
            )
        )
        if "write" not in allowed_actions(role or ""):
            raise ErrForbidden()
        user = await self.session.scalar(
            select(User.user_id).where(User.user_id == job.actor_user_id).with_for_update()
        )
        if user is None:
            raise ErrForbidden()
        bug = await self.session.scalar(
            select(Bug.bug_id)
            .where(Bug.bug_id == job.bug_id, Bug.project_id == job.project_id)
            .with_for_update()
        )
        if bug is None:
            raise ErrNotFound()
        service = await self.session.scalar(
            select(SharedService)
            .where(
                SharedService.service_id == job.service_id,
                SharedService.project_id == job.project_id,
                SharedService.provider == "mcp",
                SharedService.template_id == "zentao",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if service is None:
            raise ErrForbidden()
        connection = await self.session.scalar(
            select(IntegrationConnection)
            .join(
                ServiceAuthorization,
                ServiceAuthorization.connection_id == IntegrationConnection.connection_id,
            )
            .where(
                ServiceAuthorization.service_id == service.service_id,
                ServiceAuthorization.user_id == job.actor_user_id,
                IntegrationConnection.connection_id == job.connection_id,
                IntegrationConnection.user_id == job.actor_user_id,
                IntegrationConnection.project_id == job.project_id,
                IntegrationConnection.provider == "mcp",
                IntegrationConnection.status == "active",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if connection is None or not (connection.secret_json or {}).get("token"):
            raise ErrForbidden()
        revision = digest(
            {
                "actor": job.actor_user_id,
                "service": service.service_id,
                "endpoint": service.base_url,
                "instance": service.zentao_instance_url,
                "connection": connection.connection_id,
                "status": connection.status,
                # Credential replacement changes this digest without persisting plaintext.
                "credentialRevision": digest(connection.secret_json),
            }
        )
        return IntegrationAuthority(service, connection, revision)

    async def authorize(self, job: IntegrationJob) -> None:
        await self.authority(job)

    async def access(self, job: IntegrationJob | IntegrationSubject) -> IntegrationAccess:
        authority = await self.authority(job)
        ciphertext = (authority.connection.secret_json or {}).get("token")
        if not isinstance(ciphertext, str):
            raise ErrForbidden()
        try:
            token = self.cipher.decrypt(ciphertext)
        except (ValueError, TypeError):
            raise ErrForbidden() from None
        if not token.strip():
            raise ErrForbidden()
        return IntegrationAccess(
            authority.service.base_url, SecretStr(token), authority.access_revision
        )

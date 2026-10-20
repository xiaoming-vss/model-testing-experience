from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, select

from testing_agent.core.config import Settings, get_settings
from testing_agent.core.enums import AccountStatus, AuthSource
from testing_agent.core.errors import (
    ErrBadRequest,
    ErrCannotDeleteSelf,
    ErrCannotDisableSelf,
    ErrEmailAlreadyUse,
    ErrEmailRequired,
    ErrForbidden,
    ErrLdapReadOnly,
    ErrNotFound,
    ErrPasswordSameAsOld,
    ErrSuperAdminProtected,
)
from testing_agent.core.security import hash_password, verify_password
from testing_agent.domain.account_policy import normalize_email, validate_password
from testing_agent.models.api_environment_var import ApiEnvironmentVar
from testing_agent.models.integration_connection import IntegrationConnection
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.revoked_access_token import RevokedAccessToken
from testing_agent.models.shared_service import ServiceAuthorization
from testing_agent.models.user import User
from testing_agent.repositories.project import ProjectRepository
from testing_agent.repositories.user import UserRepository
from testing_agent.schemas.admin_user import AdminUserResponse
from testing_agent.services.auth_mode import AuthModeService
from testing_agent.services.auth_session import invalidate_sessions
from testing_agent.services.common import paged_payload
from testing_agent.services.worker_authorization import revoke_executions


class UserAdminService:
    def __init__(
        self,
        users: UserRepository,
        projects: ProjectRepository,
        settings: Settings | None = None,
        mode: AuthModeService | None = None,
    ):
        self.users = users
        self.projects = projects
        self.settings = settings or get_settings()
        self.mode = mode

    async def list(
        self,
        actor_id: str,
        *,
        search: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        await self._require_super_admin(actor_id)
        if status not in ("", "active", "disabled", "pending_ldap"):
            raise ErrBadRequest()
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        rows, total = await self.users.list_admin(
            search=search.strip(), status=status, page=page, page_size=page_size
        )
        return paged_payload([self._dump(row) for row in rows], total)

    async def disable(self, actor_id: str, target_id: str, reason: str = "") -> dict:
        await self._require_super_admin(actor_id)
        target = await self._target_for_update(target_id)
        if target.is_super_admin:
            raise ErrSuperAdminProtected()
        if target.user_id == actor_id:
            raise ErrCannotDisableSelf()
        reason = reason.strip()
        if len(reason) > 512:
            raise ErrBadRequest()
        if target.status != "disabled":
            target.status = "disabled"
            target.disabled_at = datetime.now(UTC)
            target.disabled_reason = reason
            target.disabled_by = actor_id
            invalidate_sessions(target)
        elif reason:
            target.disabled_reason = reason
        await self.users.commit()
        return self._dump(target)

    async def enable(self, actor_id: str, target_id: str) -> dict:
        await self._require_super_admin(actor_id)
        if self.mode is not None:
            await self.mode.require_current(for_update=True)
        target = await self._target_for_update(target_id)
        if target.is_super_admin:
            raise ErrSuperAdminProtected()
        target.status = (
            "pending_ldap"
            if self.settings.ldap.enabled and target.auth_source == "local"
            else "active"
        )
        target.disabled_at = None
        target.disabled_reason = ""
        target.disabled_by = ""
        if target.status == "active":
            target.failed_login_count = 0
            target.locked_until = None
            await self.users.clear_login_limits(target.nickname)
        await self.users.commit()
        return self._dump(target)

    async def reset_password(self, actor_id: str, target_id: str, new_password: str) -> dict:
        await self._require_super_admin(actor_id)
        target = await self._target_for_update(target_id)
        if target.auth_source == "ldap":
            raise ErrLdapReadOnly()
        validate_password(new_password)
        if await asyncio.to_thread(verify_password, new_password, target.password):
            raise ErrPasswordSameAsOld()
        target.password = await asyncio.to_thread(hash_password, new_password)
        target.password_updated_at = datetime.now(UTC)
        target.must_change_password = False
        invalidate_sessions(target)
        target.failed_login_count = 0
        target.locked_until = None
        await self.users.clear_login_limits(target.nickname)
        await self.users.commit()
        return self._dump(target)

    async def revoke_sessions(self, actor_id: str, target_id: str) -> dict:
        await self._require_super_admin(actor_id)
        target = await self._target_for_update(target_id)
        invalidate_sessions(target)
        await self.users.commit()
        return {}

    async def update_email(self, actor_id: str, target_id: str, email: str) -> dict:
        await self._require_super_admin(actor_id)
        target = await self._target_for_update(target_id)
        if target.auth_source == "ldap":
            raise ErrLdapReadOnly()
        new_email = normalize_email(email)
        if not new_email:
            raise ErrEmailRequired()
        if len(new_email) > 100:
            raise ErrBadRequest()
        if new_email != target.email:
            existing = await self.users.get_by_email(new_email)
            if existing is not None and existing.user_id != target.user_id:
                raise ErrEmailAlreadyUse()
            target.email = new_email
        await self.users.commit()
        return self._dump(target)

    async def delete(self, actor_id: str, target_id: str) -> dict:
        await self._require_super_admin(actor_id)
        session = self.users.session
        target = await self._target_for_update(target_id)
        if target.is_super_admin:
            raise ErrSuperAdminProtected()
        if target.user_id == actor_id:
            raise ErrCannotDeleteSelf()
        try:
            owned = list(
                (
                    await session.scalars(
                        select(Project).where(Project.user_id == target.user_id).with_for_update()
                    )
                ).all()
            )
            for project in owned:
                await session.execute(
                    delete(ProjectMember).where(
                        ProjectMember.project_id == project.project_id,
                        ProjectMember.user_id == actor_id,
                    )
                )
                if await self.projects.get_active_by_user_and_name(actor_id, project.name):
                    project.name = await self._unique_project_name(
                        actor_id, project.name, target.nickname
                    )
                project.user_id = actor_id
                await session.flush()
            await session.execute(
                delete(ProjectMember).where(ProjectMember.user_id == target.user_id)
            )
            await revoke_executions(session, actor=target.user_id)
            await session.execute(
                delete(ServiceAuthorization).where(ServiceAuthorization.user_id == target.user_id)
            )
            connections = list(
                (
                    await session.scalars(
                        select(IntegrationConnection).where(
                            IntegrationConnection.user_id == target.user_id
                        )
                    )
                ).all()
            )
            for connection in connections:
                await self.users.hard_delete(connection)
            await session.execute(
                delete(ApiEnvironmentVar).where(ApiEnvironmentVar.secret_user_id == target.user_id)
            )
            await session.execute(
                delete(RevokedAccessToken).where(RevokedAccessToken.user_id == target.user_id)
            )
            await self.users.clear_login_limits(target.nickname)
            await self.users.delete(target)
            await self.users.commit()
        except Exception:
            await session.rollback()
            raise
        return {}

    async def _unique_project_name(self, actor_id: str, name: str, target_name: str) -> str:
        suffix = f"-{target_name}"
        candidate = _truncate_name(name, suffix)
        if await self.projects.get_active_by_user_and_name(actor_id, candidate) is None:
            return candidate
        index = 2
        while True:
            candidate = _truncate_name(name, f"-{index}")
            if await self.projects.get_active_by_user_and_name(actor_id, candidate) is None:
                return candidate
            index += 1

    async def _require_super_admin(self, actor_id: str) -> None:
        actor = await self.users.get_by_user_id(actor_id)
        if actor is None or not actor.is_super_admin:
            raise ErrForbidden()

    async def _target_for_update(self, target_id: str) -> User:
        target = await self.users.get_by_user_id_for_update(target_id)
        if target is None:
            raise ErrNotFound()
        return target

    def _dump(self, user: User) -> dict:
        return AdminUserResponse(
            user_id=user.user_id,
            name=user.nickname,
            email=user.email,
            status=AccountStatus(user.status),
            auth_source=AuthSource(user.auth_source),
            is_super_admin=bool(user.is_super_admin),
            must_change_password=bool(user.must_change_password),
            disabled_at=user.disabled_at,
            disabled_reason=user.disabled_reason,
            created_at=user.created_at,
            updated_at=user.updated_at,
        ).model_dump(by_alias=True, mode="json")


def _truncate_name(name: str, suffix: str) -> str:
    maximum = 100
    if len(suffix) >= maximum:
        suffix = suffix[: maximum - 1]
    return (name[: maximum - len(suffix)] + suffix)[:maximum]

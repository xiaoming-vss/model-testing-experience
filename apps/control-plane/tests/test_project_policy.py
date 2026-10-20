"""The documented role matrix, including explicit admin differences by entry point."""

import pytest
from sqlalchemy import delete, select, update
from test_integration_authorization import db as db  # noqa: F401
from test_integration_authorization import job

from testing_agent.core.errors import AppError
from testing_agent.domain.project_policy import ACTIONS
from testing_agent.models.project import Project
from testing_agent.models.project_member import ProjectMember
from testing_agent.models.user import User
from testing_agent.services.integration_authorization import IntegrationAuthorization
from testing_agent.services.integration_recovery import lock_recovery
from testing_agent.services.project_access import require_project_access

ROLE_ACTIONS = {
    "owner": set(ACTIONS),
    "member": {"read", "write", "execute", "review", "project_read", "bug_read", "bug_handle"},
    "viewer": {"read", "project_read", "bug_read"},
    "developer": {"project_read", "bug_read", "bug_handle"},
    "nonmember": set(),
}


@pytest.mark.parametrize("role", ROLE_ACTIONS)
async def test_project_access_matrix_uses_database_membership(db, role):
    sessions, _ = db
    async with sessions() as session:
        actor = "owner" if role == "owner" else "member"
        if role == "nonmember":
            await session.execute(delete(ProjectMember).where(ProjectMember.user_id == actor))
        elif role != "owner":
            await session.execute(
                update(ProjectMember).where(ProjectMember.user_id == actor).values(role=role)
            )
        await session.commit()
        project = await session.scalar(select(Project).where(Project.project_id == "p"))
        assert project is not None
        for action in ACTIONS:
            if action in ROLE_ACTIONS[role]:
                assert await require_project_access(session, actor, project, action) == role
            else:
                with pytest.raises(AppError) as error:
                    await require_project_access(session, actor, project, action)
                assert error.value.http_code == 403


async def test_admin_override_is_only_for_interactive_access_and_recovery(db):
    sessions, cipher = db
    async with sessions() as session:
        await session.execute(
            update(User).where(User.user_id == "member").values(is_super_admin=True)
        )
        await session.execute(
            update(ProjectMember).where(ProjectMember.user_id == "member").values(role="viewer")
        )
        # Recovery queries the execution ledger even when no job exists.
        from testing_agent.models.integration_job import (
            IntegrationJob,
            IntegrationRestoreReview,
            IntegrationRuntime,
        )

        connection = await session.connection()
        for model in (IntegrationJob, IntegrationRuntime, IntegrationRestoreReview):
            await connection.run_sync(model.__table__.create, checkfirst=True)
        await session.commit()
        project = await session.scalar(select(Project).where(Project.project_id == "p"))
        assert project is not None
        assert await require_project_access(session, "member", project, "manage") == "owner"
        await lock_recovery(session, "b", "member")
        with pytest.raises(AppError) as error:
            await IntegrationAuthorization(session, cipher).access(job())
        assert error.value.http_code == 403


async def test_disabled_actor_keeps_existing_execution_but_deleted_actor_does_not(db):
    sessions, cipher = db
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.user_id == "member"))
        assert user is not None and user.user_id == "member"
        user.status = "disabled"
        await session.commit()
        authorization = IntegrationAuthorization(session, cipher)
        assert (await authorization.access(job())).token.get_secret_value() == "member-secret"
        await session.delete(user)
        await session.commit()
        with pytest.raises(AppError) as error:
            await authorization.access(job())
        assert error.value.http_code == 403

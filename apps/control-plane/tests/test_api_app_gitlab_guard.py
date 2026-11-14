"""GitLab group unbind protection for interface applications."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from testing_agent.core.errors import AppError, ErrGroupBindingInUse
from testing_agent.models import Base
from testing_agent.models.api_app import ApiApp
from testing_agent.models.project import Project
from testing_agent.services.gitlab_bindings import GitLabBindings
from testing_agent.services.service_instance import instance_key


@compiles(LONGTEXT, "sqlite")
def _sqlite_longtext(type_, compiler, **kwargs):
    return "TEXT"


class _Repository:
    def __init__(self, session, binding):
        self.session = session
        self.binding = binding

    async def get_active_project_group_binding(self, *args, **kwargs):
        return self.binding

    async def list_active_requirement_repo_bindings_for_group(self, *args, **kwargs):
        return []


def test_group_unbind_is_blocked_by_app_repository_reference():
    engine = create_async_engine("sqlite+aiosqlite://")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(Project(project_id="project-1", user_id="owner", name="项目"))
            session.add(
                ApiApp(
                    app_id="app-1",
                    project_id="project-1",
                    name="订单服务",
                    description="",
                    base_path="/api/v2",
                    repository_project_id="repo-1",
                    repository_path="commerce/order-service",
                    repository_name="order-service",
                    repository_instance_url="https://gitlab.example.com",
                    enabled=True,
                    version=1,
                    created_by_user_id="owner",
                )
            )
            await session.commit()

            binding = type(
                "Binding",
                (),
                {
                    "binding_id": "binding-1",
                    "instance_url": "https://gitlab.example.com",
                    "instance_key": instance_key("https://gitlab.example.com"),
                    "remote_resource_type": "group",
                    "remote_resource_id": "group-1",
                    "remote_name_snapshot": "commerce",
                },
            )()
            bindings = GitLabBindings(
                _Repository(session, binding),
                None,
                authorize=lambda *args, **kwargs: None,
                id_factory=lambda: "",
            )
            with pytest.raises(AppError) as captured:
                await bindings.guard_delete(binding, "project-1")
            assert captured.value.code == ErrGroupBindingInUse.code
            assert captured.value.data["apps"] == [
                {
                    "appId": "app-1",
                    "name": "订单服务",
                    "repositoryPath": "commerce/order-service",
                }
            ]

    asyncio.run(run())
    asyncio.run(engine.dispose())

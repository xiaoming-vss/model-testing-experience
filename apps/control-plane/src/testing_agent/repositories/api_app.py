from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_, select

from testing_agent.models.api_app import ApiApp
from testing_agent.models.api_interface import ApiInterface
from testing_agent.repositories.base import BaseRepository


class ApiAppRepository(BaseRepository):
    async def get(self, app_id: str) -> ApiApp | None:
        return await self.session.scalar(select(ApiApp).where(ApiApp.app_id == app_id))

    async def get_for_update(self, app_id: str) -> ApiApp | None:
        statement = (
            select(ApiApp)
            .where(ApiApp.app_id == app_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def get_by_project_and_name(
        self, project_id: str, name: str, *, exclude_app_id: str = ""
    ) -> ApiApp | None:
        statement = select(ApiApp).where(
            ApiApp.project_id == project_id,
            ApiApp.name == name,
        )
        if exclude_app_id:
            statement = statement.where(ApiApp.app_id != exclude_app_id)
        return await self.session.scalar(statement.limit(1))

    async def list_by_project(self, project_id: str) -> list[ApiApp]:
        counts = (
            select(
                ApiInterface.app_id.label("app_id"),
                func.count(ApiInterface.id).label("interface_count"),
                func.sum(case((ApiInterface.enabled.is_(True), 1), else_=0)).label(
                    "enabled_interface_count"
                ),
            )
            .group_by(ApiInterface.app_id)
            .subquery()
        )
        statement = (
            select(
                ApiApp,
                func.coalesce(counts.c.interface_count, 0).label("interface_count"),
                func.coalesce(counts.c.enabled_interface_count, 0).label("enabled_interface_count"),
            )
            .outerjoin(counts, counts.c.app_id == ApiApp.app_id)
            .where(ApiApp.project_id == project_id)
            .order_by(ApiApp.enabled.desc(), ApiApp.name.asc(), ApiApp.id.asc())
        )
        rows = (await self.session.execute(statement)).all()
        apps: list[ApiApp] = []
        for app, interface_count, enabled_interface_count in rows:
            app.interface_count = int(interface_count or 0)
            app.enabled_interface_count = int(enabled_interface_count or 0)
            apps.append(app)
        return apps

    async def count_interfaces(self, app_id: str, *, enabled: bool | None = None) -> int:
        conditions: list[Any] = [ApiInterface.app_id == app_id]
        if enabled is not None:
            conditions.append(ApiInterface.enabled.is_(enabled))
        return int(
            await self.session.scalar(select(func.count(ApiInterface.id)).where(*conditions)) or 0
        )

    async def list_repository_references(
        self,
        instance_url: str,
        group_path: str,
        *,
        project_id: str,
    ) -> list[ApiApp]:
        conditions: list[Any] = [
            ApiApp.project_id == project_id,
            ApiApp.repository_instance_url == instance_url,
            ApiApp.repository_path != "",
        ]
        if group_path:
            conditions.append(
                or_(
                    ApiApp.repository_path == group_path,
                    ApiApp.repository_path.startswith(f"{group_path}/", autoescape=True),
                )
            )
        return list(
            (
                await self.session.scalars(
                    select(ApiApp).where(*conditions).order_by(ApiApp.id.asc())
                )
            ).all()
        )

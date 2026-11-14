from __future__ import annotations

from typing import Any

from sqlalchemy import delete, exists, func, or_, select

from testing_agent.domain.api_interface_query import ApiInterfaceQuery
from testing_agent.models.api_app import ApiApp
from testing_agent.models.api_interface import ApiInterface
from testing_agent.models.api_interface_requirement import ApiInterfaceRequirement
from testing_agent.models.requirement import Requirement
from testing_agent.models.sprint import Sprint
from testing_agent.repositories.base import BaseRepository


def _like_pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class ApiInterfaceRepository(BaseRepository):
    async def get(self, interface_id: str) -> ApiInterface | None:
        return await self.session.scalar(
            select(ApiInterface).where(ApiInterface.interface_id == interface_id)
        )

    async def get_for_update(self, interface_id: str) -> ApiInterface | None:
        statement = (
            select(ApiInterface)
            .where(ApiInterface.interface_id == interface_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def get_by_identity(self, app_id: str, method: str, path_key: str) -> ApiInterface | None:
        return await self.session.scalar(
            select(ApiInterface).where(
                ApiInterface.app_id == app_id,
                ApiInterface.method == method,
                ApiInterface.path_key == path_key,
            )
        )

    async def get_by_identity_for_update(
        self, app_id: str, method: str, path_key: str
    ) -> ApiInterface | None:
        statement = (
            select(ApiInterface)
            .where(
                ApiInterface.app_id == app_id,
                ApiInterface.method == method,
                ApiInterface.path_key == path_key,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def list_by_project(self, query: ApiInterfaceQuery) -> tuple[list[ApiInterface], int]:
        conditions = self._conditions(query)
        return await self._list(conditions, query)

    async def list_by_app(
        self, app_id: str, query: ApiInterfaceQuery
    ) -> tuple[list[ApiInterface], int]:
        conditions = self._conditions(query, app_id=app_id)
        return await self._list(conditions, query)

    def _conditions(self, query: ApiInterfaceQuery, *, app_id: str = "") -> list[Any]:
        conditions: list[Any] = []
        if query.project_id:
            conditions.append(ApiApp.project_id == query.project_id)
        resolved_app_id = app_id or query.app_id
        if resolved_app_id:
            conditions.append(ApiInterface.app_id == resolved_app_id)
        if query.method:
            conditions.append(ApiInterface.method == query.method)
        if query.enabled is not None:
            conditions.append(ApiInterface.enabled.is_(query.enabled))
        if query.keyword:
            pattern = _like_pattern(query.keyword)
            conditions.append(
                or_(
                    ApiInterface.name.like(pattern, escape="\\"),
                    ApiInterface.path.like(pattern, escape="\\"),
                )
            )
        if query.requirement_id:
            conditions.append(
                exists(
                    select(1).where(
                        ApiInterfaceRequirement.interface_id == ApiInterface.interface_id,
                        ApiInterfaceRequirement.requirement_id == query.requirement_id,
                    )
                )
            )
        if query.sprint_id:
            conditions.append(
                exists(
                    select(1)
                    .select_from(ApiInterfaceRequirement)
                    .join(
                        Requirement,
                        Requirement.requirement_id == ApiInterfaceRequirement.requirement_id,
                    )
                    .where(
                        ApiInterfaceRequirement.interface_id == ApiInterface.interface_id,
                        Requirement.sprint_id == query.sprint_id,
                    )
                )
            )
        return conditions

    async def _list(
        self, conditions: list[Any], query: ApiInterfaceQuery
    ) -> tuple[list[ApiInterface], int]:
        total = int(
            await self.session.scalar(
                select(func.count(ApiInterface.id))
                .join(ApiApp, ApiApp.app_id == ApiInterface.app_id)
                .where(*conditions)
            )
            or 0
        )
        statement = (
            select(ApiInterface, ApiApp.name.label("app_name"))
            .join(ApiApp, ApiApp.app_id == ApiInterface.app_id)
            .where(*conditions)
            .order_by(ApiInterface.updated_at.desc(), ApiInterface.id.desc())
            .limit(query.limit)
            .offset(query.offset)
        )
        rows = (await self.session.execute(statement)).all()
        interfaces: list[ApiInterface] = []
        for interface, app_name in rows:
            interface.app_name = app_name
            interfaces.append(interface)
        await self.attach_requirements(interfaces)
        return interfaces, total

    async def list_all_by_app(self, app_id: str) -> list[ApiInterface]:
        return list(
            (
                await self.session.scalars(
                    select(ApiInterface)
                    .where(ApiInterface.app_id == app_id)
                    .order_by(ApiInterface.id.asc())
                )
            ).all()
        )

    async def attach_requirements(self, interfaces: list[ApiInterface]) -> None:
        if not interfaces:
            return
        ids = [interface.interface_id for interface in interfaces]
        rows = (
            await self.session.execute(
                select(ApiInterfaceRequirement.interface_id, Requirement, Sprint)
                .join(
                    Requirement,
                    Requirement.requirement_id == ApiInterfaceRequirement.requirement_id,
                )
                .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                .where(ApiInterfaceRequirement.interface_id.in_(ids))
                .order_by(Requirement.name.asc(), Requirement.id.asc())
            )
        ).all()
        by_interface: dict[str, list[dict[str, str]]] = {id_value: [] for id_value in ids}
        for interface_id, requirement, sprint in rows:
            by_interface[interface_id].append(
                {
                    "requirement_id": requirement.requirement_id,
                    "name": requirement.name,
                    "sprint_id": sprint.sprint_id,
                    "sprint_name": sprint.name,
                }
            )
        for interface in interfaces:
            interface.requirements = by_interface.get(interface.interface_id, [])

    async def requirements_by_ids(
        self, project_id: str, requirement_ids: list[str]
    ) -> list[tuple[Requirement, Sprint]]:
        if not requirement_ids:
            return []
        rows = (
            await self.session.execute(
                select(Requirement, Sprint)
                .join(Sprint, Sprint.sprint_id == Requirement.sprint_id)
                .where(
                    Requirement.requirement_id.in_(requirement_ids),
                    Sprint.project_id == project_id,
                )
                .order_by(Requirement.name.asc(), Requirement.id.asc())
            )
        ).all()
        return [(requirement, sprint) for requirement, sprint in rows]

    async def replace_requirements(
        self, interface_id: str, requirements: list[tuple[Requirement, Sprint]]
    ) -> None:
        await self.session.execute(
            delete(ApiInterfaceRequirement).where(
                ApiInterfaceRequirement.interface_id == interface_id
            )
        )
        for requirement, _sprint in requirements:
            self.session.add(
                ApiInterfaceRequirement(
                    interface_id=interface_id,
                    requirement_id=requirement.requirement_id,
                )
            )

    async def delete_requirements(self, interface_id: str) -> None:
        await self.session.execute(
            delete(ApiInterfaceRequirement).where(
                ApiInterfaceRequirement.interface_id == interface_id
            )
        )

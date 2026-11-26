from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import defer

from testing_agent.models.ui_element import UiElement, UiElementGroup
from testing_agent.repositories.base import BaseRepository
from testing_agent.schemas.ui_element import UiElementListFilters


class UiElementRepository(BaseRepository):
    async def groups(self, repository_id: str) -> list[tuple[UiElementGroup, int]]:
        statement = (
            select(UiElementGroup, func.count(UiElement.id))
            .outerjoin(UiElement, UiElement.group_id == UiElementGroup.group_id)
            .where(UiElementGroup.software_repository_id == repository_id)
            .group_by(UiElementGroup.id)
            .order_by(UiElementGroup.kind, UiElementGroup.name, UiElementGroup.id)
        )
        return [(group, count) for group, count in await self.session.execute(statement)]

    async def group(
        self, group_id: str, *, repository_id: str | None = None, for_update: bool = False
    ) -> UiElementGroup | None:
        statement = select(UiElementGroup).where(UiElementGroup.group_id == group_id)
        if repository_id is not None:
            statement = statement.where(UiElementGroup.software_repository_id == repository_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def find_group(
        self, repository_id: str, kind: str, route_key: str
    ) -> UiElementGroup | None:
        return await self.session.scalar(
            select(UiElementGroup)
            .where(
                UiElementGroup.software_repository_id == repository_id,
                UiElementGroup.kind == kind,
                UiElementGroup.route_key == route_key,
            )
            .with_for_update()
        )

    async def group_has_elements(self, group_id: str) -> bool:
        row_id = await self.session.scalar(
            select(UiElement.id).where(UiElement.group_id == group_id).limit(1).with_for_update()
        )
        return row_id is not None

    async def list_elements(
        self, repository_id: str, filters: UiElementListFilters
    ) -> tuple[list[UiElement], int]:
        statement = select(UiElement).join(
            UiElementGroup, UiElementGroup.group_id == UiElement.group_id
        )
        statement = statement.where(UiElementGroup.software_repository_id == repository_id)
        if filters.group_id is not None:
            statement = statement.where(UiElement.group_id == filters.group_id)
        if filters.verification_status:
            statement = statement.where(
                UiElement.verification_status == filters.verification_status
            )
        if keyword := filters.keyword.strip():
            statement = statement.where(
                UiElement.name.icontains(keyword, autoescape=True)
                | UiElement.scope.icontains(keyword, autoescape=True)
                | UiElement.locator_value.icontains(keyword, autoescape=True)
            )
        identities = statement.with_only_columns(UiElement.id).subquery()
        total = await self.session.scalar(select(func.count()).select_from(identities))
        statement = (
            statement.options(defer(UiElement.locator_value))
            .order_by(UiElement.updated_at.desc(), UiElement.id.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return list(await self.session.scalars(statement)), total or 0

    async def element_repository_id(self, element_id: str) -> str | None:
        return await self.session.scalar(
            select(UiElementGroup.software_repository_id)
            .join(UiElement, UiElement.group_id == UiElementGroup.group_id)
            .where(UiElement.element_id == element_id)
        )

    async def element(self, element_id: str, *, for_update: bool = False) -> UiElement | None:
        statement = select(UiElement).where(UiElement.element_id == element_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(statement)

    async def element_with_locator(self, group_id: str, locator_key: str) -> UiElement | None:
        return await self.session.scalar(
            select(UiElement)
            .where(UiElement.group_id == group_id, UiElement.locator_key == locator_key)
            .with_for_update()
        )

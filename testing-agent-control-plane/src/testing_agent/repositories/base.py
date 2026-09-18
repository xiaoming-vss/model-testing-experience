"""Repository session helpers and resource lookup.

Deletion is always physical; resource lookups use business identity directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.db.base import Base


class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def hard_delete(self, obj: Any) -> None:
        from testing_agent.repositories.deletion import delete_resource

        await delete_resource(self.session, obj)

    def add(self, obj: Any) -> None:
        self.session.add(obj)

    def add_all(self, objs: list[Any]) -> None:
        self.session.add_all(objs)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, obj: Any) -> None:
        await self.session.refresh(obj)

    async def flush(self) -> None:
        await self.session.flush()


class ResourceRepository(BaseRepository):
    """资源通用查询；子类声明 model 与 id_column（业务键列名）。"""

    model: type[Base]
    id_column: str

    async def get_active_by_id(self, id_value: str) -> Any | None:
        # 经 model 类取列(InstrumentedAttribute),避免实例属性访问触发 ORM 描述符
        id_col = getattr(self.model, self.id_column)
        row = await self.session.scalar(select(self.model).where(id_col == id_value))
        return row

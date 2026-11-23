"""Bounded reads for independent import provenance."""

from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from testing_agent.core.errors import ErrBadRequest
from testing_agent.models.ai_generate_import import AiGenerateImport


async def import_schema_installed(session: AsyncSession) -> bool:
    def tables(sync: Session) -> set[str]:
        key = "generation_import_tables"
        if key not in sync.info:
            sync.info[key] = set(inspect(sync.connection()).get_table_names()) & {
                "ai_generate_import_requests",
                "ai_generate_imports",
            }
        return sync.info[key]

    present = await session.run_sync(tables)
    if present and len(present) != 2:
        raise ErrBadRequest()
    return bool(present)


async def standalone_imports(session: AsyncSession):
    if not await import_schema_installed(session):
        raise ErrBadRequest()
    return (
        select(
            AiGenerateImport.import_id,
            AiGenerateImport.source_attempt_id.label("attempt_id"),
            AiGenerateImport.target_type,
            AiGenerateImport.target_id,
            AiGenerateImport.imported_at,
        )
        .where(
            AiGenerateImport.source_kind == "standalone",
            AiGenerateImport.source_attempt_id.is_not(None),
        )
        .subquery()
    )


async def import_records(session: AsyncSession, attempt_id: str) -> list[Any]:
    imports = await standalone_imports(session)
    rows = await session.execute(
        select(imports)
        .where(imports.c.attempt_id == attempt_id)
        .order_by(imports.c.imported_at, imports.c.import_id)
    )
    return list(rows)

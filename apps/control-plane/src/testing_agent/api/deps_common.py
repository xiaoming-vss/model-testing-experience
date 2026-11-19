from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from testing_agent.core.config import Settings, get_settings
from testing_agent.db.session import get_session


def get_file_service(
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)
):
    from testing_agent.services.stored_file import StoredFileService

    return StoredFileService(session, settings.s3)

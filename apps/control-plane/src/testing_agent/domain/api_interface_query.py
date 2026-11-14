from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiInterfaceQuery:
    """Project or app scoped interface filters for one stable page."""

    project_id: str = ""
    app_id: str = ""
    method: str = ""
    requirement_id: str = ""
    sprint_id: str = ""
    enabled: bool | None = None
    keyword: str = ""
    limit: int = 20
    offset: int = 0

    @classmethod
    def for_page(
        cls,
        *,
        page: int,
        page_size: int,
        project_id: str = "",
        app_id: str = "",
        method: str = "",
        requirement_id: str = "",
        sprint_id: str = "",
        enabled: bool | None = None,
        keyword: str = "",
    ) -> ApiInterfaceQuery:
        return cls(
            project_id=project_id.strip(),
            app_id=app_id.strip(),
            method=method.strip().upper(),
            requirement_id=requirement_id.strip(),
            sprint_id=sprint_id.strip(),
            enabled=enabled,
            keyword=keyword.strip(),
            limit=page_size,
            offset=(page - 1) * page_size,
        )

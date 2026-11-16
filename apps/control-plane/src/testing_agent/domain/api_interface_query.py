from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiInterfaceQuery:
    """Project or software repository scoped interface filters for one stable page."""

    project_id: str = ""
    software_repository_id: str = ""
    method: str = ""
    requirement_id: str = ""
    sprint_id: str = ""
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
        software_repository_id: str = "",
        method: str = "",
        requirement_id: str = "",
        sprint_id: str = "",
        keyword: str = "",
    ) -> ApiInterfaceQuery:
        return cls(
            project_id=project_id.strip(),
            software_repository_id=software_repository_id.strip(),
            method=method.strip().upper(),
            requirement_id=requirement_id.strip(),
            sprint_id=sprint_id.strip(),
            keyword=keyword.strip(),
            limit=page_size,
            offset=(page - 1) * page_size,
        )

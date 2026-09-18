from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.zentao.imports import (
    first_value,
    normalize_datetime,
    normalize_optional_int,
    normalize_optional_str,
    normalize_required_int,
    normalize_required_str,
)


class BugImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    openedDate: str | None = None
    resolvedDate: str | None = None
    status: str | None = None
    type: str | None = None
    pri: int | None = None
    severity: int | None = None
    title: str
    plan: int | None = None
    execution: int | None = None
    module: int | None = None
    product: int | None = None

    @classmethod
    def from_upstream(cls, item: dict[str, Any]) -> "BugImportData":
        return cls(
            id=normalize_required_int(item.get("id")),
            openedDate=normalize_datetime(first_value(item, "openedDate", "opened_date")),
            resolvedDate=normalize_datetime(first_value(item, "resolvedDate", "resolved_date")),
            status=normalize_optional_str(item.get("status")),
            type=normalize_optional_str(item.get("type")),
            pri=normalize_optional_int(item.get("pri")),
            severity=normalize_optional_int(item.get("severity")),
            title=normalize_required_str(item.get("title")),
            plan=normalize_optional_int(item.get("plan")),
            execution=normalize_optional_int(item.get("execution")),
            module=normalize_optional_int(item.get("module")),
            product=normalize_optional_int(item.get("product")),
        )

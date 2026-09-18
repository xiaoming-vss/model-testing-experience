from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

try:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    SHANGHAI_TZ = timezone(timedelta(hours=8))
EMPTY_TIME_VALUES = {"", "0000-00-00", "0000-00-00 00:00:00"}


class ImportListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)

    def to_zentao_params(self) -> dict[str, str | int]:
        return {
            "browseType": "all",
            "recPerPage": self.page_size,
            "pageID": self.page,
        }


class ImportListData[T](BaseModel):
    items: list[T]
    total: int


class ProjectImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    code: str | None = None
    description: str | None = None
    status: str | None = None
    begin: str | None = None
    end: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted: bool = False

    @classmethod
    def from_upstream(cls, item: dict[str, Any]) -> "ProjectImportData":
        return cls(
            id=normalize_required_int(item.get("id")),
            name=normalize_required_str(item.get("name")),
            code=normalize_optional_str(item.get("code")),
            description=normalize_description(item),
            status=normalize_optional_str(item.get("status")),
            begin=normalize_datetime(item.get("begin")),
            end=normalize_datetime(item.get("end")),
            created_at=normalize_datetime(
                first_value(item, "created_at", "createdAt", "createdDate")
            ),
            updated_at=normalize_datetime(
                first_value(item, "updated_at", "updatedAt", "lastEditedDate", "editedDate")
            ),
            deleted=normalize_bool(item.get("deleted")),
        )


class ExecutionImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    name: str
    description: str | None = None
    status: str | None = None
    begin: str | None = None
    end: str | None = None
    parent_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted: bool = False

    @classmethod
    def from_upstream(
        cls,
        item: dict[str, Any],
        *,
        fallback_project_id: int | None = None,
    ) -> "ExecutionImportData":
        return cls(
            id=normalize_required_int(item.get("id")),
            project_id=normalize_required_int(
                first_value(item, "project_id", "project", default=fallback_project_id)
            ),
            name=normalize_required_str(item.get("name")),
            description=normalize_description(item),
            status=normalize_optional_str(item.get("status")),
            begin=normalize_datetime(item.get("begin")),
            end=normalize_datetime(item.get("end")),
            parent_id=normalize_optional_int(first_value(item, "parent_id", "parent")),
            created_at=normalize_datetime(
                first_value(item, "created_at", "createdAt", "createdDate")
            ),
            updated_at=normalize_datetime(
                first_value(item, "updated_at", "updatedAt", "lastEditedDate", "editedDate")
            ),
            deleted=normalize_bool(item.get("deleted")),
        )


class StoryImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    product_id: int | None = None
    module_id: int | None = None
    plan_id: int | None = None
    status: str | None = None
    stage: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    opened_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted: bool = False

    @classmethod
    def from_upstream(cls, item: dict[str, Any]) -> "StoryImportData":
        return cls(
            id=normalize_required_int(item.get("id")),
            title=normalize_required_str(first_value(item, "title", "name")),
            product_id=normalize_optional_int(first_value(item, "product_id", "product")),
            module_id=normalize_optional_int(first_value(item, "module_id", "module")),
            plan_id=normalize_optional_int(first_value(item, "plan_id", "plan")),
            status=normalize_optional_str(item.get("status")),
            stage=normalize_optional_str(item.get("stage")),
            priority=normalize_priority(first_value(item, "priority", "pri")),
            assigned_to=normalize_optional_str(first_value(item, "assigned_to", "assignedTo")),
            opened_by=normalize_optional_str(first_value(item, "opened_by", "openedBy")),
            created_at=normalize_datetime(
                first_value(item, "created_at", "createdDate", "openedDate")
            ),
            updated_at=normalize_datetime(
                first_value(item, "updated_at", "lastEditedDate", "editedDate")
            ),
            deleted=normalize_bool(item.get("deleted")),
        )


class TestTaskImportData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int | None = None
    execution_id: int | None = None
    name: str
    title: str | None = None
    description: str | None = None
    status: str | None = None
    type: str | None = None
    owner: str | None = None
    opened_by: str | None = None
    begin: str | None = None
    end: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted: bool = False

    @classmethod
    def from_upstream(
        cls,
        item: dict[str, Any],
        *,
        fallback_execution_id: int | None = None,
    ) -> "TestTaskImportData":
        name = normalize_required_str(first_value(item, "name", "title"))
        title = normalize_optional_str(item.get("title"))
        if title == name:
            title = None
        return cls(
            id=normalize_required_int(item.get("id")),
            project_id=normalize_optional_int(first_value(item, "project_id", "project")),
            execution_id=normalize_optional_int(
                first_value(item, "execution_id", "execution", default=fallback_execution_id)
            ),
            name=name,
            title=title,
            description=normalize_description(item),
            status=normalize_optional_str(item.get("status")),
            type=normalize_optional_str(item.get("type")),
            owner=normalize_optional_str(item.get("owner")),
            opened_by=normalize_optional_str(first_value(item, "opened_by", "openedBy")),
            begin=normalize_datetime(item.get("begin")),
            end=normalize_datetime(item.get("end")),
            created_at=normalize_datetime(
                first_value(item, "created_at", "createdAt", "createdDate")
            ),
            updated_at=normalize_datetime(
                first_value(item, "updated_at", "updatedAt", "lastEditedDate", "editedDate")
            ),
            deleted=normalize_bool(item.get("deleted")),
        )


def extract_total(payload: dict[str, Any], fallback: int) -> int:
    value = first_value(payload, "total", "count")
    if value is None:
        pager = payload.get("pager")
        if isinstance(pager, dict):
            value = pager.get("recTotal")
    total = normalize_optional_int(value)
    return fallback if total is None else total


def first_value(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return default


def normalize_description(item: dict[str, Any]) -> str | None:
    return normalize_optional_str(first_value(item, "description", "desc"))


def normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value)
    if normalized in EMPTY_TIME_VALUES:
        return None
    return normalized


def normalize_required_str(value: Any) -> str:
    normalized = normalize_optional_str(value)
    return "" if normalized is None else normalized


def normalize_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_required_int(value: Any) -> int:
    normalized = normalize_optional_int(value)
    return 0 if normalized is None else normalized


def normalize_priority(value: Any) -> str | None:
    priority = normalize_optional_str(value)
    if priority is None:
        return None
    upper_priority = priority.upper()
    if upper_priority.startswith("P"):
        return upper_priority
    return f"P{priority}"


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return bool(text)


def normalize_datetime(value: Any) -> str | None:
    text = normalize_optional_str(value)
    if text is None:
        return None

    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime.combine(parsed_date, time.min, tzinfo=SHANGHAI_TZ).isoformat()

        normalized_text = text.replace("Z", "+00:00")
        if "T" in normalized_text:
            parsed = datetime.fromisoformat(normalized_text)
        else:
            parsed = datetime.strptime(normalized_text, "%Y-%m-%d %H:%M:%S")

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
        return parsed.isoformat()
    except ValueError:
        return text

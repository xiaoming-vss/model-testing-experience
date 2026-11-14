from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiInterfaceImportWarning(BaseModel):
    code: str
    message: str
    method: str = ""
    path: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportSource(BaseModel):
    type: str = "openapi_file"
    name: str = ""
    url: str = ""
    version: str = ""
    digest: str = ""
    base_path: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportApp(BaseModel):
    app_id: str
    name: str
    base_path: str = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportSummary(BaseModel):
    new: int = 0
    modified: int = 0
    unchanged: int = 0
    library_only: int = 0

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportBasePathChange(BaseModel):
    current: str = ""
    document: str = ""
    can_apply: bool = False

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportItem(BaseModel):
    key: str
    change_type: str
    method: str
    path: str
    name: str
    existing_interface_id: str | None = None
    existing_version: int | None = None
    changed_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportPreviewResponse(BaseModel):
    source: ApiInterfaceImportSource
    app: ApiInterfaceImportApp
    summary: ApiInterfaceImportSummary
    base_path_change: ApiInterfaceImportBasePathChange | None = None
    warnings: list[ApiInterfaceImportWarning] = Field(default_factory=list)
    items: list[ApiInterfaceImportItem] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportResultItem(BaseModel):
    key: str
    interface_id: str
    change_type: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiInterfaceImportCommitResponse(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    library_only: int = 0
    app_base_path: str = ""
    interfaces: list[ApiInterfaceImportResultItem] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

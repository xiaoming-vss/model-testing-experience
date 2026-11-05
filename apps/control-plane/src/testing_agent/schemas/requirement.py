from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from testing_agent.schemas.resource_binding import ZentaoBindingSummaryResponse

# 需求文档只支持富文本与 Word/DOCX；历史 TXT 已通过迁移转换为富文本。
DOCUMENT_TYPES = {"docx", "richtext"}
DOCUMENT_TYPE_ALIASES = {"word": "docx"}


def normalize_document_type(value: str) -> str:
    normalized = DOCUMENT_TYPE_ALIASES.get(value, value)
    if normalized not in DOCUMENT_TYPES:
        raise ValueError("documentType must be docx or richtext")
    return normalized


class CreateRequirementRequest(BaseModel):
    name: str
    document_type: str = Field(default="richtext")
    document_file_id: str = Field(default="", max_length=64)
    document_content: str = Field(default="")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        return normalize_document_type(value)


class UpdateRequirementRequest(BaseModel):
    name: str | None = None
    document_type: str | None = Field(default=None)
    document_file_id: str | None = Field(default=None, max_length=64)
    document_content: str | None = Field(default=None)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_document_type(value)


class RequirementMetadataResponse(BaseModel):
    requirement_id: str = Field()
    sprint_id: str = Field()
    name: str
    document_type: str = Field(default="richtext")
    document_file_id: str = Field(default="", max_length=64)
    document_filename: str = Field(default="")
    document_hash: str = Field(default="")
    document_download_url: str = Field(default="")
    created_at: datetime | str | None = Field(default="")
    updated_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        return normalize_document_type(value)


class RequirementResponse(RequirementMetadataResponse):
    document_content: str = Field(default="")


class RequirementCodeSummaryResponse(BaseModel):
    repository: str
    branch: str


class RequirementOptionResponse(BaseModel):
    """下拉选项只带识别与展示字段，刻意不包含 document_content。"""

    requirement_id: str = Field()
    sprint_id: str = Field()
    sprint_name: str
    name: str
    document_filename: str = Field(default="")
    created_at: datetime | str | None = Field(default="")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)


class RequirementListItemResponse(RequirementMetadataResponse):
    sprint_name: str
    zentao_binding: ZentaoBindingSummaryResponse | None = None
    code_bindings: list[RequirementCodeSummaryResponse] = Field(default_factory=list)

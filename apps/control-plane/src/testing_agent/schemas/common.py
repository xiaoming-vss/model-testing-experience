from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

DataT = TypeVar("DataT")


class ApiResponse[DataT](BaseModel):
    code: int = 0
    message: str = "ok"
    data: DataT
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ListResponse[DataT](BaseModel):
    total: int = 0
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    items: list[DataT]


class EmptyData(BaseModel):
    model_config = ConfigDict(extra="forbid", alias_generator=to_camel)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MessageData(BaseModel):
    message: str

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StatusData(BaseModel):
    status: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UrlData(BaseModel):
    url: str

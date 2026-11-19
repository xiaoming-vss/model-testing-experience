"""UI Worker artifact upload protocol models."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class WorkerFileRequest(BaseModel):
    worker_id: str
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerFileCompleteRequest(BaseModel):
    worker_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

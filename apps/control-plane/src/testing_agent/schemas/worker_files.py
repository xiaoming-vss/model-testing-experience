"""UI Worker artifact upload protocol models."""

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class WorkerFileRequest(StrictRequest):
    worker_id: str
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f]+$")
    size: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WorkerFileCompleteRequest(StrictRequest):
    worker_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

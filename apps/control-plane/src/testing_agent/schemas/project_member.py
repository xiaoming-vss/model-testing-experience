from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from testing_agent.schemas.common import StrictRequest


class AddProjectMemberRequest(StrictRequest):
    name: str
    role: Literal["member", "viewer", "developer"]


class ProjectMemberResponse(BaseModel):
    user_id: str
    name: str
    role: Literal["owner", "member", "viewer", "developer"]
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChangeProjectMemberRequest(StrictRequest):
    role: Literal["member", "viewer", "developer"]


class TransferProjectRequest(StrictRequest):
    user_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

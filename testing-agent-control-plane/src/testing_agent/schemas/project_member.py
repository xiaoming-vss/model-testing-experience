from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AddProjectMemberRequest(BaseModel):
    name: str
    role: Literal["member", "viewer"]


class ProjectMemberResponse(BaseModel):
    user_id: str
    name: str
    role: Literal["owner", "member", "viewer"]
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChangeProjectMemberRequest(BaseModel):
    role: Literal["member", "viewer"]


class TransferProjectRequest(BaseModel):
    user_id: str
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

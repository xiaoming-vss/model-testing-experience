from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class SkillFileInput(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    path: str = Field(min_length=1, max_length=512)
    file_id: str = Field(min_length=1, max_length=64)


class ProjectSkillUploadRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    files: list[SkillFileInput] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_files(self):
        paths, ids = set(), set()
        for entry in self.files:
            path = entry.path
            if (
                "\\" in path
                or any(ord(c) < 32 for c in path)
                or any(p in {"", ".", ".."} for p in path.split("/"))
                or ":" in path
                or path.casefold() in paths
                or entry.file_id in ids
            ):
                raise ValueError("技能文件路径重复或不合法")
            paths.add(path.casefold())
            ids.add(entry.file_id)
        if not any(entry.path == "SKILL.md" for entry in self.files):
            raise ValueError("技能根目录必须包含 SKILL.md")
        for path in paths:
            parts = path.split("/")
            if any("/".join(parts[:i]) in paths for i in range(1, len(parts))):
                raise ValueError("文件与目录路径冲突")
        return self


class ProjectSkillSpaceResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    skill_space_id: str
    project_id: str | None = None
    filename: str
    hash: str
    size: int
    file_count: int
    is_default: bool
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None

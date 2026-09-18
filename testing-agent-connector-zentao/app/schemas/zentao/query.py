from pydantic import BaseModel, ConfigDict, Field

from app.schemas.zentao.imports import ImportListQuery


class ZentaoQueryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=1)


class ZentaoListQuery(ZentaoQueryBase):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)

    def to_service_query(self) -> ImportListQuery:
        return ImportListQuery(page=self.page, page_size=self.page_size)


class ZentaoDetailQuery(ZentaoQueryBase):
    pass

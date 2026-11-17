from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

MonitoringAuthType = Literal["none", "basic", "bearer", "headers"]


class MonitoringAuthRequest(BaseModel):
    type: MonitoringAuthType = "none"
    username: str = ""
    password: SecretStr = SecretStr("")
    token: SecretStr = SecretStr("")
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def _auth_fields(self) -> MonitoringAuthRequest:
        if self.type == "basic":
            if not self.username.strip():
                raise ValueError("basic 认证必须提供 username")
            if not self.password.get_secret_value():
                raise ValueError("basic 认证必须提供 password")
            if self.headers:
                raise ValueError("basic 认证不能提供 headers")
        elif self.type == "bearer":
            if not self.token.get_secret_value():
                raise ValueError("bearer 认证必须提供 token")
            if self.headers:
                raise ValueError("bearer 认证不能提供 headers")
        elif self.type == "headers":
            if not self.headers:
                raise ValueError("headers 认证必须提供 headers")
            for name, value in self.headers.items():
                if not name.strip() or any(char in name for char in ":\r\n"):
                    raise ValueError("认证 header 名称不合法")
                if "\r" in value or "\n" in value:
                    raise ValueError("认证 header 值不能包含换行")
        else:
            if self.username or self.password.get_secret_value() or self.token.get_secret_value():
                raise ValueError("none 认证不能提供凭据")
            if self.headers:
                raise ValueError("none 认证不能提供 headers")
        return self


def _validate_http_url(value: str, *, field: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"{field} 必须是 http(s) URL")
    if parts.username or parts.password:
        raise ValueError(f"{field} 不能包含用户名或密码")
    if parts.query or parts.fragment:
        raise ValueError(f"{field} 不能包含查询或片段")
    return value.rstrip("/")


class MonitoringConnectionCreate(BaseModel):
    name: str
    remote_write_url: str
    remote_write_auth: MonitoringAuthRequest = Field(default_factory=MonitoringAuthRequest)
    enabled: bool = True

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 120:
            raise ValueError("名称长度必须在 1 到 120 个字符之间")
        return value

    @field_validator("remote_write_url")
    @classmethod
    def _required_url(cls, value: str, info: Any) -> str:
        return _validate_http_url(value, field=info.field_name)


class MonitoringConnectionUpdate(BaseModel):
    name: str | None = None
    remote_write_url: str | None = None
    remote_write_auth: MonitoringAuthRequest | None = None
    enabled: bool | None = None

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or len(value) > 120:
            raise ValueError("名称长度必须在 1 到 120 个字符之间")
        return value

    @field_validator("remote_write_url")
    @classmethod
    def _required_url(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _validate_http_url(value, field=info.field_name)


class MonitoringConnectionResponse(BaseModel):
    connection_id: str
    project_id: str
    name: str
    remote_write_url: str
    remote_write_auth_type: MonitoringAuthType
    has_remote_write_credentials: bool
    enabled: bool
    created_at: datetime | str | None = ""
    updated_at: datetime | str | None = ""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

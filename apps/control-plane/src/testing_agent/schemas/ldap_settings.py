from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from testing_agent.core.ldap_config import LdapSettings


class LdapConfigInput(LdapSettings):
    """Admin input uses the runtime structure and adds a write-only secret field."""

    bind_password: SecretStr | None = None  # type: ignore[assignment]

    def configuration(self) -> dict:
        data = self.model_dump(exclude={"bind_password"}, exclude_unset=True)
        if self.bind_password is not None:
            data["bind_password"] = self.bind_password.get_secret_value()
        return data


class SaveLdapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation: int = Field(ge=0)
    config: LdapConfigInput
    clearPassword: bool = False


class TestLdapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: LdapConfigInput
    username: str = Field(default="", max_length=50)
    clearPassword: bool = False


class LdapConfigView(LdapConfigInput):
    require_bind_password: ClassVar[bool] = False
    bind_password: SecretStr | None = Field(default=None, exclude=True)


class LdapSettingsResponse(BaseModel):
    generation: int
    source: str
    passwordConfigured: bool
    config: LdapConfigView


class LdapTestResponse(BaseModel):
    connected: bool
    message: str
    userFound: bool | None = None
    eligible: bool | None = None
    emailPresent: bool | None = None

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LdapConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    server_url: str = Field(default="", max_length=2048)
    start_tls: bool = True
    allow_insecure_connection: bool = False
    tls_ca_file: str = Field(default="", max_length=2048)
    tls_ca_pem: str = Field(default="", max_length=65536)
    bind_dn: str = Field(default="", max_length=2048)
    bind_password: SecretStr | None = None
    user_search_base: str = Field(default="", max_length=2048)
    user_search_filter: str = Field(default="(uid={username})", max_length=4096)
    access_group_dn: str = Field(default="", max_length=2048)
    username_attribute: str = "uid"
    email_attribute: str = "mail"
    external_id_attribute: str = "entryUUID"
    group_member_attribute: str = "memberUid"
    group_member_value_type: str = "username"
    timeout_seconds: int = 5
    login_timeout_seconds: int = 30
    reconcile_interval_seconds: int = 300
    auto_link_by_username: bool = False
    token_expire_hours: int = 12
    directory_rules_verified: bool = False
    active_user_filter: str = Field(default="", max_length=4096)
    disabled_user_filter: str = Field(default="", max_length=4096)

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

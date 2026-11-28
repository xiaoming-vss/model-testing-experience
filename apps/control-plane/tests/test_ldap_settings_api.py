from unittest.mock import AsyncMock, patch

from support.ldap_settings_admin import config
from support.local_account_management import super_admin
from support.project_api import account, api  # noqa: F401


def test_admin_page_config_secret_redaction_live_policy_and_ordinary_denial(api):  # noqa: F811
    _, user_headers = account(api, "ordinary")
    _, admin_headers = super_admin(api)
    assert api.get("/v1/admin/ldap", headers=user_headers).status_code == 403
    before = api.get("/v1/admin/ldap", headers=admin_headers)
    assert before.status_code == 200
    version = before.json()["data"]["generation"]
    body = config()
    body["bind_password"] = "only-in-test-request-secret"
    saved = api.put(
        "/v1/admin/ldap", headers=admin_headers, json={"generation": version, "config": body}
    )
    assert saved.status_code == 200, saved.text
    assert "only-in-test-request-secret" not in saved.text
    assert "bind_password" not in saved.json()["data"]["config"]
    assert saved.json()["data"]["passwordConfigured"]
    assert api.get("/v1/auth/config").json()["data"] == {
        "ldapEnabled": True,
        "registrationEnabled": False,
        "localLoginAdminOnly": True,
    }
    assert api.get("/v1/user", headers=user_headers).status_code == 401
    assert api.get("/v1/user", headers=admin_headers).status_code == 200
    assert (
        api.put(
            "/v1/admin/ldap", headers=admin_headers, json={"generation": version, "config": body}
        ).status_code
        == 409
    )
    version = saved.json()["data"]["generation"]
    disabled = api.put(
        "/v1/admin/ldap",
        headers=admin_headers,
        json={"generation": version, "config": {"enabled": False}},
    )
    assert disabled.status_code == 200, disabled.text
    assert api.get("/v1/auth/config").json()["data"]["ldapEnabled"] is False
    assert api.get("/v1/user", headers=user_headers).status_code == 401


def test_connection_test_is_readonly_and_uses_draft(api):  # noqa: F811
    _, headers = super_admin(api)
    with patch("testing_agent.services.ldap_settings.LdapDirectory") as directory:
        directory.return_value.check_connection = AsyncMock()
        response = api.post("/v1/admin/ldap/test", headers=headers, json={"config": config()})
    assert response.status_code == 200, response.text
    current = api.get("/v1/admin/ldap", headers=headers).json()["data"]
    assert current["source"] == "database" and not current["config"]["enabled"]


def test_blank_bind_password_keeps_the_saved_secret(api):  # noqa: F811
    """The admin form submits a blank password to keep the stored one."""
    _, headers = super_admin(api)
    body = {**config(), "bind_password": "only-in-test-request-secret"}
    version = api.get("/v1/admin/ldap", headers=headers).json()["data"]["generation"]
    saved = api.put("/v1/admin/ldap", headers=headers, json={"generation": version, "config": body})
    assert saved.status_code == 200, saved.text
    version = saved.json()["data"]["generation"]
    blank = {**config(), "bind_password": ""}
    kept = api.put("/v1/admin/ldap", headers=headers, json={"generation": version, "config": blank})
    assert kept.status_code == 200, kept.text
    assert kept.json()["data"]["passwordConfigured"]

    with patch("testing_agent.services.ldap_settings.LdapDirectory") as directory:
        directory.return_value.check_connection = AsyncMock()
        tested = api.post("/v1/admin/ldap/test", headers=headers, json={"config": blank})
    assert tested.status_code == 200, tested.text


def test_enabling_without_any_password_is_rejected_by_the_service(api):  # noqa: F811
    _, headers = super_admin(api)
    body = {**config(), "bind_password": ""}
    version = api.get("/v1/admin/ldap", headers=headers).json()["data"]["generation"]
    rejected = api.put(
        "/v1/admin/ldap", headers=headers, json={"generation": version, "config": body}
    )
    assert rejected.status_code == 400, rejected.text

from testing_agent.core.config import Settings


def test_default_http_port_matches_deployment():
    settings = Settings.from_mapping({})
    assert settings.http_host == "127.0.0.1"
    assert settings.http_port == 9000


def test_explicit_http_port_is_preserved():
    settings = Settings.from_mapping({"http": {"host": "0.0.0.0", "port": 19000}})
    assert settings.http_host == "0.0.0.0"
    assert settings.http_port == 19000

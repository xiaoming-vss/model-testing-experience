"""Test layers for the development gate; no collected cases.

The full suite is the delivery gate. During development skip the layers that
need live resources or a real MySQL database:

    uv run --locked --extra dev pytest -q -m "not mysql and not live"

Markers are derived from the fixtures a test requests, its parametrized MySQL
variant and its file name, so a test module picks up its layer without
repeating a marker declaration:

- mysql: needs CONTROL_PLANE_TEST_DATABASE_URL pointing at a disposable MySQL database
- live: needs CONTROL_PLANE_STORAGE_LIVE and a real object store
- api: drives the HTTP boundary through create_app and SQLite
- contract: pins worker or HTTP protocol shapes
- arch: enforces module layering rules
- unit: domain and application behavior with in-memory collaborators

A module can override the derivation by declaring one of these markers itself.
"""

from __future__ import annotations

import pytest

CONTRACT_FILES = {
    "test_app_contract.py",
    "test_auth_contract.py",
    "test_full_route_parity.py",
    "test_go_field_contracts.py",
    "test_worker_contract.py",
}
LAYERS = ("mysql", "live", "api", "contract", "arch", "unit")


def _layer(item: pytest.Item) -> str:
    fixtures = set(item.fixturenames)
    callspec = getattr(item, "callspec", None)
    # A fixture parametrized over ("sqlite", "mysql") resolves the MySQL fixture at
    # runtime, so the MySQL variant only shows up in the callspec during collection.
    parameterized_mysql = callspec is not None and "mysql" in callspec.params.values()
    name = item.path.name
    if "mysql" in fixtures or parameterized_mysql:
        return "mysql"
    if "live" in fixtures:
        return "live"
    if "api" in fixtures:
        return "api"
    if name in CONTRACT_FILES or "_contract" in name:
        return "contract"
    if name == "test_architecture_layers.py":
        return "arch"
    return "unit"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if any(item.get_closest_marker(layer) for layer in LAYERS):
            continue
        item.add_marker(getattr(pytest.mark, _layer(item)))

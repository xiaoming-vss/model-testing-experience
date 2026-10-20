"""Pure field-update identity and comparison shared by execution and recovery."""

from collections.abc import Mapping
from typing import Any

FIELD_UPDATE_KEY = "_fieldUpdate"


def fields_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        set(left["openedBuild"]) == set(right["openedBuild"])
        and left["assignedTo"] == right["assignedTo"]
    )

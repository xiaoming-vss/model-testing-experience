from typing import Any


class FieldsError(Exception):
    pass


def fields(remote: dict[str, Any]) -> dict[str, Any]:
    builds = remote.get("openedBuild")
    if isinstance(builds, str):
        builds = builds.split(",")
    assignee = remote.get("assignedTo")
    if "assignedTo" in remote and assignee is None:
        assignee = ""
    if isinstance(assignee, dict):
        assignee = assignee.get("account")
    if (
        not isinstance(builds, list)
        or not builds
        or any(not isinstance(item, (str, int)) or isinstance(item, bool) for item in builds)
        or not isinstance(assignee, str)
    ):
        raise FieldsError("Remote Bug fields cannot be safely compared")
    return {
        "openedBuild": list(dict.fromkeys(str(item) for item in builds)),
        "assignedTo": assignee,
    }


def equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        set(left["openedBuild"]) == set(right["openedBuild"])
        and left["assignedTo"] == right["assignedTo"]
    )


def changes(before: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in desired.items()
        if (set(value) != set(before[key]) if key == "openedBuild" else value != before[key])
    }

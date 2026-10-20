"""The real API preserves ZenTao's status, confirmation and resolution semantics."""

import pytest
from support.bug_api import activities_of, create_bug, get_bug, transition
from support.function_case_library import make_sprint
from support.project_api import account, project
from support.project_api import api as api


@pytest.fixture
def lifecycle(api):
    user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint = make_sprint(api, owner, pid)
    bug = create_bug(api, owner, pid, sprint, reporter=user)
    return owner, pid, sprint, user, bug


def test_confirmation_is_independent_and_activation_preserves_it(api, lifecycle):
    owner, _, _, _, bug = lifecycle
    bid = bug["bugId"]
    confirmed = transition(api, owner, bid, "confirm").json()["data"]
    assert confirmed["status"] == "active" and confirmed["confirmed"]
    assert transition(api, owner, bid, "confirm").json()["code"] == 3702
    resolved = transition(
        api, owner, bid, "resolve", resolution="fixed", resolvedBuild="v1.2", content="修复阈值"
    ).json()["data"]
    assert resolved["status"] == "resolved" and resolved["resolution"] == "fixed"
    assert resolved["resolvedBuild"] == "v1.2"
    assert (
        transition(api, owner, bid, "close", content="验证通过").json()["data"]["status"]
        == "closed"
    )
    active = transition(api, owner, bid, "activate", content="再次复现").json()["data"]
    assert active["status"] == "active" and active["confirmed"]
    assert active["resolution"] == active["resolvedBuild"] == ""
    assert active["activatedCount"] == 1
    events = activities_of(api, owner, bid)["items"]
    assert events[1]["detail"]["fromConfirmed"] is False
    assert events[1]["detail"]["toConfirmed"] is True
    assert events[2]["detail"]["resolvedBuild"] == "v1.2"
    assert events[-1]["detail"]["fromResolution"] == "fixed"
    assert events[-1]["detail"]["toResolution"] == ""


@pytest.mark.parametrize(
    "resolution", ["bydesign", "external", "notrepro", "postponed", "willnotfix", "tostory"]
)
def test_non_fix_resolution_is_not_a_fix_or_a_closed_bug(api, lifecycle, resolution):
    owner, pid, _, _, bug = lifecycle
    result = transition(
        api, owner, bug["bugId"], "resolve", resolution=resolution, content="处理结论"
    ).json()["data"]
    assert result["status"] == "resolved" and result["resolution"] == resolution
    assert not result["confirmed"]
    assert result["resolvedBuild"] == ""
    filtered = api.get(
        f"/v1/projects/{pid}/bugs?status=active,resolved&resolution={resolution}&confirmed=false",
        headers=owner,
    ).json()["data"]
    assert filtered["total"] == 1
    assert (
        api.get(f"/v1/projects/{pid}/bugs?resolution=fixed", headers=owner).json()["data"]["total"]
        == 0
    )
    assert (
        transition(api, owner, bug["bugId"], "close", content="确认处理结论").json()["data"][
            "resolution"
        ]
        == resolution
    )


@pytest.mark.parametrize(
    "fields,message",
    [
        ({"resolution": "fixed"}, "解决版本"),
        ({"resolution": "invalid"}, "解决方案"),
        ({"resolution": "duplicate"}, "重复 Bug"),
        ({"resolution": "bydesign", "duplicateBug": 999}, "仅重复"),
        ({"resolution": "postponed", "resolvedBuild": "v1.2"}, "解决版本"),
    ],
)
def test_invalid_resolution_input_changes_neither_bug_nor_history(api, lifecycle, fields, message):
    owner, _, _, _, bug = lifecycle
    result = transition(api, owner, bug["bugId"], "resolve", content="处理说明", **fields)
    assert result.status_code == 400 and message in result.json()["message"]
    current = get_bug(api, owner, bug["bugId"])
    assert current["status"] == "active" and current["resolution"] == ""
    assert len(activities_of(api, owner, bug["bugId"])["items"]) == 1


def test_duplicate_requires_a_different_bug_in_the_same_project(api, lifecycle):
    owner, pid, sprint, user, bug = lifecycle
    other = create_bug(api, owner, pid, sprint, reporter=user)
    assert (
        transition(
            api,
            owner,
            bug["bugId"],
            "resolve",
            resolution="duplicate",
            duplicateBug=bug["id"],
            content="重复",
        ).status_code
        == 400
    )
    foreign_pid = project(api, owner, "foreign")
    foreign = create_bug(
        api, owner, foreign_pid, make_sprint(api, owner, foreign_pid), reporter=user
    )
    assert (
        transition(
            api,
            owner,
            bug["bugId"],
            "resolve",
            resolution="duplicate",
            duplicateBug=foreign["id"],
            content="重复",
        ).status_code
        == 400
    )
    result = transition(
        api,
        owner,
        bug["bugId"],
        "resolve",
        resolution="duplicate",
        duplicateBug=other["id"],
        content="同一问题",
    ).json()["data"]
    assert result["duplicateBug"] == other["id"] and result["resolution"] == "duplicate"
    active = transition(api, owner, bug["bugId"], "activate", content="不是同一问题").json()["data"]
    assert active["duplicateBug"] == 0


def test_illegal_actions_and_legacy_filters_are_rejected(api, lifecycle):
    owner, pid, _, _, bug = lifecycle
    bid = bug["bugId"]
    for action in ("close", "activate"):
        assert transition(api, owner, bid, action, content="说明").json()["code"] == 3702
    assert transition(api, owner, bid, "confirm", resolution="fixed").status_code == 400
    assert not get_bug(api, owner, bid)["confirmed"]
    assert api.get(f"/v1/projects/{pid}/bugs?status=pending", headers=owner).status_code == 400
    assert api.get(f"/v1/projects/{pid}/bugs?resolution=invalid", headers=owner).status_code == 400

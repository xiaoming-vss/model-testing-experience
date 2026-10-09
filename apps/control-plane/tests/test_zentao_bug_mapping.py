"""共享禅道 Bug 转换口径：等级/优先级/状态映射、快照规范化与描述图片检测。"""

import pytest

from testing_agent.domain.zentao_bug_mapping import (
    check_title,
    has_remote_images,
    map_priority,
    map_severity,
    map_status,
    remote_description,
    remote_snapshot,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", "fatal"), (2, "serious"), ("3", "normal"), ("4.0", "minor")],
)
def test_severity_mapping(raw, expected):
    assert map_severity(raw) == expected


@pytest.mark.parametrize("raw", ["", "0", "5", None])
def test_severity_unmapped_values_stay_pending(raw):
    assert map_severity(raw) is None


def test_priority_maps_all_four_levels_losslessly():
    # 2026-10-09 四档对齐：紧急/高/中/低 ↔ 1/2/3/4，优先级不再有待映射。
    assert map_priority("1") == "urgent"
    assert map_priority(2) == "high"
    assert map_priority("3") == "medium"
    assert map_priority("4.0") == "low"
    assert map_priority("") is None


def test_status_keeps_platform_triple_when_resolvable():
    assert map_status("active", "0", "") == {
        "status": "active",
        "confirmed": False,
        "resolution": "",
        "resolvedBuild": "",
    }
    assert map_status("resolved", "1", "fixed", "v2") == {
        "status": "resolved",
        "confirmed": True,
        "resolution": "fixed",
        "resolvedBuild": "v2",
    }
    assert map_status("closed", "1", "notrepro")["status"] == "closed"


@pytest.mark.parametrize(
    ("status", "resolution"),
    [("processing", ""), ("resolved", ""), ("closed", "unknown")],
)
def test_status_unresolvable_combinations_stay_pending(status, resolution):
    # resolved/closed 缺少解决方案、未知状态或未知方案都不能猜测（R24）。
    assert map_status(status, "1", resolution) is None


def test_title_checks_length_without_truncation():
    assert check_title(" 标题 ") == "标题"
    with pytest.raises(ValueError):
        check_title("")
    with pytest.raises(ValueError):
        check_title("长" * 201)


def test_remote_snapshot_normalizes_contract_shapes():
    snapshot = remote_snapshot(
        {
            "id": "42",
            "title": "登录失败",
            "severity": 1,
            "priority": "3",
            "status": "resolved",
            "confirmed": "1",
            "resolution": "fixed",
            "resolvedBuild": "trunk",
            "duplicateBug": "",
            "activatedCount": "2",
            "assignedTo": "admin",
            "openedBy": "tester",
            "openedDate": "2026-10-01 10:00:00",
            "deleted": False,
        }
    )
    assert snapshot == {
        "remoteBugId": 42,
        "title": "登录失败",
        "severity": "1",
        "priority": "3",
        "status": "resolved",
        "confirmed": True,
        "resolution": "fixed",
        "resolvedBuild": "trunk",
        "duplicateBug": 0,
        "activatedCount": 2,
        "execution": 0,
        "story": 0,
        "project": 0,
        "assignedTo": "admin",
        "openedBy": "tester",
        "openedDate": "2026-10-01 10:00:00",
        "deleted": False,
    }


def test_remote_snapshot_rejects_invalid_identity_only():
    # 未知状态保留原值并交由 map_status 标记待处理，这里只校验编号和标题。
    with pytest.raises(ValueError):
        remote_snapshot({"id": "bad", "title": "x", "status": "active"})
    with pytest.raises(ValueError):
        remote_snapshot({"id": 1, "title": "", "status": "active"})
    assert remote_snapshot({"id": 1, "title": "x", "status": "floating"})["status"] == "floating"


def test_remote_description_flags_images_and_digests_sanitized_text():
    plain = remote_description("<p>第一行</p><p>第二行</p>")
    assert plain["hasImages"] is False
    assert plain["hasContent"] is True
    assert plain["sanitized"] == "<p>第一行</p><p>第二行</p>"

    with_image = remote_description('<p>截图</p><img src="http://zentao/file/1.png" alt=""/>')
    assert with_image["hasImages"] is True
    # src 属于外部登录地址：消毒后只剩文字，图片等待文件管线（R46）。
    assert "http" not in with_image["sanitized"]
    assert (
        with_image["digest"]
        == remote_description('<p>截图</p><img src="http://zentao/file/1.png"/>')["digest"]
    )


def test_has_remote_images_detects_void_and_explicit_close():
    assert has_remote_images('<img src="a.png"/>') is True
    assert has_remote_images("<img src='a.png'></img>") is True
    assert has_remote_images("<p>纯文本</p>") is False
    assert has_remote_images("") is False

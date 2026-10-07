"""Bug 管理：创建编号、禅道状态、确认和解决方案、转派、编辑历史、筛选分页与执行来源。"""

from test_function_case_library import make_case, make_requirement, make_sprint, make_suite
from test_project_membership_api import account, project
from test_project_membership_api import api as api

from testing_agent.domain.rich_text import extract_file_ids, sanitize_rich_text


def create_bug(api, headers, pid, sprint_id, title="登录失败", reporter=None, **overrides):
    body = {
        "title": title,
        "assigneeUserId": overrides.pop("assigneeUserId", None)
        or (reporter["userId"] if reporter else None),
        "severity": "serious",
        "priority": "high",
        "foundSprintId": sprint_id,
        "descriptionHtml": "<p>现象与复现步骤</p>",
        **overrides,
    }
    if body["assigneeUserId"] is None:
        body.pop("assigneeUserId")
    response = api.post(f"/v1/projects/{pid}/bugs", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def get_bug(api, headers, bug_id):
    response = api.get(f"/v1/bugs/{bug_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def transition(api, headers, bug_id, action, **fields):
    if action == "submit_fix":
        fields.setdefault("resolvedBuild", "trunk")
    return api.post(
        f"/v1/bugs/{bug_id}/transition", headers=headers, json={"action": action, **fields}
    )


def activities_of(api, headers, bug_id):
    response = api.get(f"/v1/bugs/{bug_id}/activities", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_assigns_project_scoped_bug_number_and_records_creation(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)

    first = create_bug(api, owner, pid, sprint_id, reporter=owner_user, title="第一个缺陷")
    second = create_bug(api, owner, pid, sprint_id, reporter=owner_user, title="第二个缺陷")
    assert first["bugNo"] == 1
    assert second["bugNo"] == 2
    assert first["status"] == "active"
    assert not first["confirmed"] and first["resolution"] == ""
    assert first["reporterUserId"] == owner_user["userId"]
    assert first["severity"] == "serious" and first["priority"] == "high"
    assert first["foundSprintId"] == sprint_id
    assert first["plannedFixSprintId"] == ""
    assert first["requirementId"] == ""

    records = activities_of(api, owner, first["bugId"])
    assert [item["kind"] for item in records["items"]] == ["status_change"]
    assert records["items"][0]["action"] == "create"
    assert records["items"][0]["toStatus"] == "active"


def test_create_validates_required_fields_and_project_scope(api):
    owner_user, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    other_pid = project(api, owner, "另一个项目")
    other_sprint = make_sprint(api, owner, other_pid)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )

    base = {"title": "缺陷", "assigneeUserId": member_user["userId"], "foundSprintId": sprint_id}
    # 责任人必填且必须是项目成员
    missing_assignee = api.post(
        f"/v1/projects/{pid}/bugs",
        headers=owner,
        json={"title": "缺陷", "foundSprintId": sprint_id},
    )
    assert missing_assignee.status_code == 400
    assert missing_assignee.json()["code"] == 3705
    assert (
        api.post(
            f"/v1/projects/{pid}/bugs",
            headers=owner,
            json={**base, "assigneeUserId": "nobody"},
        ).json()["code"]
        == 3705
    )
    # 发现迭代必须属于当前项目
    assert (
        api.post(
            f"/v1/projects/{pid}/bugs", headers=owner, json={**base, "foundSprintId": other_sprint}
        ).json()["code"]
        == 3706
    )
    # 严重程度与优先级必须是合法值
    assert (
        api.post(
            f"/v1/projects/{pid}/bugs", headers=owner, json={**base, "severity": "huge"}
        ).status_code
        == 400
    )
    assert (
        api.post(
            f"/v1/projects/{pid}/bugs", headers=owner, json={**base, "priority": "urgent"}
        ).status_code
        == 400
    )

    created = create_bug(api, owner, pid, sprint_id, assigneeUserId=member_user["userId"])
    assert created["assigneeUserId"] == member_user["userId"]


def test_full_state_machine_follows_the_transition_table(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    bug_id = create_bug(api, owner, pid, sprint_id, reporter=owner_user)["bugId"]

    # 表外组合直接拒绝
    assert transition(api, owner, bug_id, "submit_fix").json()["code"] == 3702
    assert transition(api, owner, bug_id, "regression_pass").json()["code"] == 3702

    assert transition(api, owner, bug_id, "confirm").json()["data"]["status"] == "active"
    # 提交修复必须带修复说明
    assert transition(api, owner, bug_id, "submit_fix").json()["code"] == 3704
    fixed = transition(api, owner, bug_id, "submit_fix", content="调整了阈值判断")
    assert fixed.json()["data"]["status"] == "resolved"
    # 回归失败 → 重新打开（必填失败说明）
    assert transition(api, owner, bug_id, "regression_fail").json()["code"] == 3704
    failed = transition(api, owner, bug_id, "regression_fail", content="复现步骤仍然失败")
    assert failed.json()["data"]["status"] == "active"
    assert transition(api, owner, bug_id, "confirm").json()["code"] == 3702
    assert transition(api, owner, bug_id, "submit_fix", content="第二轮修复").status_code == 200
    closed = transition(api, owner, bug_id, "regression_pass", content="回归通过")
    assert closed.json()["data"]["status"] == "closed"
    # 已关闭后仍可重新打开再次处理
    reopened = transition(api, owner, bug_id, "reopen", content="生产环境再次出现")
    assert reopened.json()["data"]["status"] == "active"

    records = activities_of(api, owner, bug_id)
    status_flow = [
        (item["fromStatus"], item["action"], item["toStatus"])
        for item in records["items"]
        if item["kind"] == "status_change" and item["action"] != "create"
    ]
    assert status_flow == [
        ("active", "confirm", "active"),
        ("active", "submit_fix", "resolved"),
        ("resolved", "regression_fail", "active"),
        ("active", "submit_fix", "resolved"),
        ("resolved", "regression_pass", "closed"),
        ("closed", "reopen", "active"),
    ]
    # 多轮修复说明全部保留
    contents = [item["content"] for item in records["items"] if item["action"] == "submit_fix"]
    assert contents == ["调整了阈值判断", "第二轮修复"]


def test_reject_requires_reason_and_rejected_can_reopen(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    bug_id = create_bug(api, owner, pid, sprint_id, reporter=owner_user)["bugId"]

    assert transition(api, owner, bug_id, "reject").json()["code"] == 3703
    assert transition(api, owner, bug_id, "reject", rejectReason="whatever").json()["code"] == 3703
    rejected = transition(
        api, owner, bug_id, "reject", rejectReason="by_design", content="与产品确认过"
    )
    assert rejected.json()["data"]["status"] == "resolved"

    records = activities_of(api, owner, bug_id)["items"]
    reject_record = [item for item in records if item["action"] == "reject"][0]
    assert reject_record["detail"]["rejectReason"] == "by_design"
    assert reject_record["detail"]["rejectReasonLabel"] == "设计如此"
    assert reject_record["content"] == "与产品确认过"

    reopened = transition(api, owner, bug_id, "reopen", content="设计变更需要重新处理")
    assert reopened.json()["data"]["status"] == "active"
    assert (
        transition(api, owner, bug_id, "reject", rejectReason="deferred").json()["data"]["status"]
        == "resolved"
    )


def test_transfer_changes_assignee_without_touching_status(api):
    owner_user, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )
    sprint_id = make_sprint(api, owner, pid)
    bug = create_bug(api, owner, pid, sprint_id, assigneeUserId=owner_user["userId"])
    assert bug["status"] == "active"

    assert (
        api.post(
            f"/v1/bugs/{bug['bugId']}/transfer",
            headers=owner,
            json={"assigneeUserId": "nobody"},
        ).json()["code"]
        == 3705
    )
    transferred = api.post(
        f"/v1/bugs/{bug['bugId']}/transfer",
        headers=owner,
        json={"assigneeUserId": member_user["userId"]},
    )
    assert transferred.status_code == 200, transferred.text
    data = transferred.json()["data"]
    assert data["assigneeUserId"] == member_user["userId"]
    assert data["status"] == "active"

    transfer_records = [
        item
        for item in activities_of(api, owner, bug["bugId"])["items"]
        if item["kind"] == "transfer"
    ]
    assert len(transfer_records) == 1
    assert transfer_records[0]["detail"]["toUserId"] == member_user["userId"]


def test_edit_records_field_history_without_status_change(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    planned_sprint = make_sprint(api, owner, pid, "修复迭代")
    requirement_id = make_requirement(api, owner, sprint_id)
    bug = create_bug(api, owner, pid, sprint_id, reporter=owner_user, title="旧标题")
    bug_id = bug["bugId"]

    updated = api.patch(
        f"/v1/bugs/{bug_id}",
        headers=owner,
        json={
            "title": "新标题",
            "severity": "fatal",
            "plannedFixSprintId": planned_sprint,
            "requirementId": requirement_id,
            "descriptionHtml": "<p>新描述</p>",
        },
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["status"] == "active"
    assert data["title"] == "新标题"
    assert data["severity"] == "fatal"
    assert data["plannedFixSprintId"] == planned_sprint
    assert data["requirementId"] == requirement_id
    assert data["requirementName"] == "req"

    # 空串表示取消关联
    cleared = api.patch(f"/v1/bugs/{bug_id}", headers=owner, json={"requirementId": ""})
    assert cleared.json()["data"]["requirementId"] == ""

    edits = [item for item in activities_of(api, owner, bug_id)["items"] if item["kind"] == "edit"]
    assert edits, "编辑应记录动态"
    assert any(
        change["field"] == "title" and change["to"] == "新标题"
        for change in edits[0]["detail"]["changes"]
    )

    # 非法枚举被拒绝
    assert (
        api.patch(f"/v1/bugs/{bug_id}", headers=owner, json={"severity": "huge"}).status_code == 400
    )


def test_list_filters_statuses_severity_assignee_and_keyword(api):
    owner_user, owner = account(api, "owner")
    member_user, member = account(api, "member")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "member", "role": "member"}
        ).status_code
        == 200
    )
    sprint_a = make_sprint(api, owner, pid, "迭代A")
    sprint_b = make_sprint(api, owner, pid, "迭代B")

    other_pid = project(api, owner, "其他项目")
    create_bug(api, owner, other_pid, make_sprint(api, owner, other_pid), reporter=owner_user)

    mine = create_bug(
        api, owner, pid, sprint_a, title="我的缺陷", assigneeUserId=owner_user["userId"]
    )
    create_bug(api, owner, pid, sprint_a, title="别人的缺陷", assigneeUserId=member_user["userId"])
    create_bug(
        api,
        owner,
        pid,
        sprint_b,
        title="致命问题",
        severity="fatal",
        assigneeUserId=member_user["userId"],
    )
    to_regress = create_bug(
        api, owner, pid, sprint_b, title="待回归", assigneeUserId=member_user["userId"]
    )
    transition(api, owner, to_regress["bugId"], "confirm")
    transition(api, owner, to_regress["bugId"], "submit_fix", content="修了")
    rejected = create_bug(
        api, owner, pid, sprint_b, title="被拒绝", assigneeUserId=member_user["userId"]
    )
    transition(api, owner, rejected["bugId"], "reject", rejectReason="deferred")

    def list_bugs(query=""):
        response = api.get(f"/v1/projects/{pid}/bugs{query}", headers=owner)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    assert list_bugs()["total"] == 5
    # 迭代筛选：默认按发现迭代
    assert list_bugs(f"?sprintId={sprint_a}")["total"] == 2
    # 多状态筛选
    data = list_bugs("?status=resolved&resolution=fixed")
    assert [item["bugId"] for item in data["items"]] == [to_regress["bugId"]]
    # 严重程度筛选
    assert list_bugs("?severity=fatal")["total"] == 1
    # 责任人筛选
    assert list_bugs(f"?assigneeUserId={member_user['userId']}")["total"] == 4
    # 关键词命中标题
    assert list_bugs("?keyword=致命")["total"] == 1
    # 跨项目自增主键与项目内编号不同；数字搜索必须命中列表展示的主键。
    assert mine["id"] != mine["bugNo"]
    data = list_bugs(f"?keyword={mine['id']}")
    assert data["total"] == 1
    assert data["items"][0]["id"] == mine["id"]
    assert data["items"][0]["bugId"] == mine["bugId"]
    assert get_bug(api, owner, mine["bugId"])["id"] == mine["id"]
    # 分页
    paged = list_bugs("?page=2&pageSize=2")
    assert paged["total"] == 5
    assert len(paged["items"]) == 2


def test_submit_bug_from_execution_record_auto_links_and_snapshots(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    requirement_id = make_requirement(api, owner, sprint_id)
    suite_id = make_suite(api, owner, requirement_id)
    case_id = make_case(api, owner, suite_id, title="登录成功")
    order_response = api.post(
        f"/v1/sprints/{sprint_id}/test-orders", headers=owner, json={"name": "冒烟测试单"}
    )
    assert order_response.status_code == 200, order_response.text
    order_id = order_response.json()["data"]["orderId"]
    assert (
        api.post(
            f"/v1/test-orders/{order_id}/cases", headers=owner, json={"caseIds": [case_id]}
        ).status_code
        == 200
    )
    entry = api.get(f"/v1/test-orders/{order_id}/entries", headers=owner).json()["data"]["items"][0]
    # 条目响应带所属需求，供提交 Bug 时自动带入
    assert entry["requirementId"] == requirement_id
    assert entry["requirementName"] == "req"

    # 先判失败再提交 Bug
    assert (
        api.patch(
            f"/v1/test-orders/{order_id}/entries/{entry['entryId']}",
            headers=owner,
            json={"status": "failed", "failureReason": "断言失败"},
        ).status_code
        == 200
    )

    created = create_bug(
        api,
        owner,
        pid,
        sprint_id,
        reporter=owner_user,
        title="登录用例失败",
        sourceEntryId=entry["entryId"],
        sourceOrderId=order_id,
        sourceCaseId=case_id,
        requirementId=requirement_id,
    )
    assert created["sourceOrderId"] == order_id
    assert created["sourceEntryId"] == entry["entryId"]
    assert created["sourceCaseId"] == case_id
    assert created["sourceOrderName"] == "冒烟测试单"
    assert created["sourceCaseTitle"] == "登录成功"

    linked = api.get(f"/v1/projects/{pid}/bugs?sourceEntryId={entry['entryId']}", headers=owner)
    assert linked.json()["data"]["total"] == 1
    assert linked.json()["data"]["items"][0]["bugId"] == created["bugId"]

    # 跨项目的执行记录不能作为来源
    other_pid = project(api, owner, "别的项目")
    foreign = api.post(
        f"/v1/projects/{other_pid}/bugs",
        headers=owner,
        json={
            "title": "跨项目来源",
            "assigneeUserId": owner_user["userId"],
            "foundSprintId": make_sprint(api, owner, other_pid),
            "sourceEntryId": entry["entryId"],
        },
    )
    assert foreign.json()["code"] == 3708


def test_comments_are_recorded_and_viewer_cannot_write(api):
    owner_user, owner = account(api, "owner")
    _, viewer = account(api, "viewer")
    pid = project(api, owner)
    assert (
        api.post(
            f"/v1/projects/{pid}/members", headers=owner, json={"name": "viewer", "role": "viewer"}
        ).status_code
        == 200
    )
    sprint_id = make_sprint(api, owner, pid)
    bug = create_bug(api, owner, pid, sprint_id, reporter=owner_user)

    commented = api.post(
        f"/v1/bugs/{bug['bugId']}/comments", headers=owner, json={"content": "补充一条日志"}
    )
    assert commented.status_code == 200, commented.text
    comments = [
        item
        for item in activities_of(api, owner, bug["bugId"])["items"]
        if item["kind"] == "comment"
    ]
    assert len(comments) == 1
    assert comments[0]["content"] == "补充一条日志"

    assert api.get(f"/v1/bugs/{bug['bugId']}", headers=viewer).status_code == 200
    assert (
        api.post(
            f"/v1/bugs/{bug['bugId']}/comments", headers=viewer, json={"content": "看看"}
        ).status_code
        == 403
    )
    assert transition(api, viewer, bug["bugId"], "confirm").status_code == 403


def test_rich_text_sanitizer_keeps_allowlisted_structure_only():
    dirty = (
        '<p onclick="evil()">现象</p>'
        "<script>alert(1)</script>"
        '<img src="https://evil" onerror="x()" data-file-id="file-1">'
        "<h2>步骤</h2><ul><li>打开页面</li></ul>"
        '<a href="https://evil">点我</a>'
    )
    clean = sanitize_rich_text(dirty)
    assert "onclick" not in clean
    assert "script" not in clean
    assert "src" not in clean
    assert "onerror" not in clean
    assert "<p>现象</p>" in clean
    assert '<img data-file-id="file-1">' in clean
    assert "<h2>步骤</h2>" in clean
    assert "<li>打开页面</li>" in clean
    assert "点我" in clean and "<a" not in clean
    assert extract_file_ids(clean) == ["file-1"]
    # 非法 file-id 被剔除
    assert extract_file_ids(sanitize_rich_text('<img data-file-id="bad id">')) == []
    # 畸形标签会被闭合
    assert sanitize_rich_text("<p><strong>加粗") == "<p><strong>加粗</strong></p>"
    assert sanitize_rich_text("") == ""


def test_description_is_required_after_sanitizing_and_history_is_not_truncated(api):
    owner_user, owner = account(api, "owner")
    pid = project(api, owner)
    sprint_id = make_sprint(api, owner, pid)
    for description in ("", "<p>&nbsp;</p>", "<script>alert(1)</script>"):
        response = api.post(
            f"/v1/projects/{pid}/bugs",
            headers=owner,
            json={
                "title": "描述校验",
                "assigneeUserId": owner_user["userId"],
                "foundSprintId": sprint_id,
                "descriptionHtml": description,
            },
        )
        assert response.status_code == 400
    before = "<p>" + "复现步骤" * 60 + "原结果</p>"
    after = "<p>" + "复现步骤" * 60 + "新结果</p>"
    bug = create_bug(api, owner, pid, sprint_id, reporter=owner_user, descriptionHtml=before)
    response = api.patch(
        f"/v1/bugs/{bug['bugId']}", headers=owner, json={"descriptionHtml": "<p><br></p>"}
    )
    assert response.status_code == 400
    assert get_bug(api, owner, bug["bugId"])["descriptionHtml"] == before
    response = api.patch(f"/v1/bugs/{bug['bugId']}", headers=owner, json={"descriptionHtml": after})
    assert response.status_code == 200
    records = activities_of(api, owner, bug["bugId"])
    edit = next(record for record in records["items"] if record["kind"] == "edit")
    assert edit["detail"]["changes"] == [{"field": "descriptionHtml", "from": before, "to": after}]


def test_remove_attachment_is_scoped_and_recorded(api):
    import asyncio
    from datetime import datetime

    from testing_agent.core.config import get_settings
    from testing_agent.models.stored_file import StoredFile

    user, headers = account(api, "attachment-owner")
    pid = project(api, headers)
    sprint = make_sprint(api, headers, pid)
    bug = create_bug(api, headers, pid, sprint, reporter=user)
    other = create_bug(api, headers, pid, sprint, reporter=user)

    async def seed():
        async with api.app.state.test_sessions() as session:
            for fid, bid in [("own-file", bug["bugId"]), ("other-file", other["bugId"])]:
                session.add(
                    StoredFile(
                        file_id=fid,
                        project_id=pid,
                        uploaded_by=user["userId"],
                        filename=f"{fid}.txt",
                        content_type="text/plain",
                        size=1,
                        sha256="a" * 64,
                        bucket=get_settings().s3.bucket,
                        object_key=fid,
                        staging_key=fid,
                        status="attached",
                        purpose="attachment",
                        resource_type="bug",
                        resource_id=bid,
                        expires_at=datetime(2020, 1, 1),
                    )
                )
            await session.commit()

    asyncio.run(seed())
    path = f"/v1/bugs/{bug['bugId']}"
    response = api.patch(path, headers=headers, json={"removedAttachmentFileIds": ["other-file"]})
    assert response.status_code == 400, response.text
    assert len(get_bug(api, headers, bug["bugId"])["attachments"]) == 1
    response = api.patch(path, headers=headers, json={"removedAttachmentFileIds": ["own-file"]})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["attachments"] == []
    assert len(get_bug(api, headers, other["bugId"])["attachments"]) == 1
    records = activities_of(api, headers, bug["bugId"])["items"]
    assert any(
        item["detail"].get("removedFiles") == [{"fileId": "own-file", "filename": "own-file.txt"}]
        for item in records
    )

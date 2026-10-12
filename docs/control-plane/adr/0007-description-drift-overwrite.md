# 正文漂移按平台内容覆盖禅道

2026-10-08，用户确认：Bug 正文图片同步不再因描述文字漂移拒绝执行。此前 Worker 在本地描述或远端描述相对推送基线变化时抛 `baseline_changed`，要求用户先手工核对两端；该守卫阻断了自己编辑描述后的正常补图（bug-zentao-push.md 记录的真实案例），且禅道自带修改历史，覆盖风险可回溯。

新策略：同步始终按平台当前内容渲染 `steps` 并经 `put_bugs_bugID` 覆盖远端正文；Worker 在步骤数据中记录 `overwrote`（`localEdited`＝本地相对基线变化，`remoteEdited`＝远端相对基线变化），控制面随 `description_sync_json` 持久化备查。2026-10-08 二次确认：界面不提示覆盖——成功状态保持安静（同步成功的常驻横幅与状态文字重复，一并移除），仅失败或未完成有提示。未知结果、一次执行、许可与回执机制（ADR 0006）不变；`previousStatus=unknown` 的只读恢复路径与旧图片编码修复限制不变。字段修改任务的远端漂移守卫维持原状，如需同样策略另立决策。

边界：覆盖以写入时刻的核对为准，不提供远端内容预览或二次确认；被覆盖的禅道侧修改依赖禅道自身操作日志回溯。相关验证见 `apps/integration-worker/tests/test_zentao_gateway.py::test_description_drift_overwrites_and_records_the_fact`、`apps/control-plane/tests/test_bug_zentao_description.py`。

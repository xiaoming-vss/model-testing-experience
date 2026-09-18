# 功能测试用例批量删除

`POST /v1/function-test-suites/{suite_id}/cases/batch-delete`

沿用登录鉴权和项目 `write` 权限（所有者、普通成员可操作，只读成员不可操作）。

请求：

```json
{"caseIds": ["case-id-1", "case-id-2"]}
```

- `caseIds` 必填，1–500 项，禁止空白 ID；重复 ID 自动去重。
- 全部 ID 必须存在且属于路径中的测试集。不存在或跨测试集返回 404，整批不删除。
- 所有删除在同一数据库事务内提交，失败整体回滚。沿用单条硬删除及附属数据清理规则。
- 不接受空列表代表“全部”，仅删除显式指定的用例。

成功使用标准 ApiResponse 封装，`data` 为：

```json
{"deletedIds": ["case-id-1", "case-id-2"], "deletedCount": 2}
```

前端成功后清理对应详情缓存、刷新用例和测试集计数；失败保留勾选供用户处理后重试。此接口不删除外部禅道用例。

验证：`pytest tests/test_function_case_batch_delete.py -q`。
部署顺序：先部署后端接口，再发布前端批量删除按钮。

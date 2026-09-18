# 项目共享服务与个人授权

基础服务采用“创建服务 → 我的授权 → 使用”的流程。

| 内容 | 项目所有者 | 普通成员 / 只读成员 |
| --- | --- | --- |
| 查看项目服务名称、地址、模型 | 可 | 可 |
| 创建、重命名、删除服务 | 可 | 不可 |
| 配置、更新、撤销自己的授权 | 可 | 可 |
| 查看或使用别人的凭据 | 不可 | 不可 |

只读成员配置授权不授予项目执行权限；实际操作仍检查原项目权限。

## 接口

前缀：`/v1/projects/{projectId}/services/{provider}`，provider 为 `llm` / `zentao` / `gitlab`。

- `GET /`：项目共享目录，每项 `authorization` 只代表当前用户。
- `POST /`：所有者提交 `name`、`baseUrl`，LLM 另有 `modelId`；拒绝凭据字段。
- `PATCH /{serviceId}`：所有者重命名。地址和模型不变，更换时创建新服务。
- `DELETE /{serviceId}`：所有者删除；关联授权失效，相关未完成任务撤销。
- `PUT /{serviceId}/authorization`：创建或更新当前用户授权。
  - LLM：`apiKey`
  - GitLab：`accessToken`
  - 禅道：`account`、`password`
- `DELETE /{serviceId}/authorization`：撤销当前用户授权，不影响其他成员。

目录响应包含 `serviceId`、`projectId`、`provider`、`name`、`baseUrl`、`modelId`，以及：

```json
{"authorization":{"status":"unauthorized","connectionId":null,"account":"","lastAuthAt":null}}
```

授权状态为 `unauthorized`（未授权）、`authorized`（已保存可用连接）或 `invalid`（个人连接失效）。
有授权时 `connectionId` 是本人的执行连接，账号和授权时间也仅来自本人。GitLab、禅道
保存授权时调用现有外部验证；LLM 沿用原 API Key 保存方式，实际调用仍可能因外部限额、
模型权限或 Key 失效而失败，不承诺保存即完成远端可用性测试。

旧 `/integrations/{provider}/connections` 查询继续只返回本人连接，供任务执行和绑定选择器使用。
授权撤销后旧 connection ID 不可再使用；重新授权生成新的个人 ID。

## 新库初始化

仅支持使用 `alembic upgrade head` 初始化全新空数据库。`20260916_0007` 只创建
共享服务及个人授权关联表，不读取或转换历史个人连接，不提供旧库兼容升级流程。
服务目录初始为空，由项目所有者创建服务，再由成员分别配置本人授权。

## 验证

空库初始化、重复初始化和回退重建由 `tests/test_initial_schema_migration.py` 验证；
共享目录、所有者管理权限及个人授权隔离由 `tests/test_shared_services_api.py` 验证。
MySQL 初始化及并发验证使用 `tests/test_mysql_initialization.py` 中的隔离测试库。

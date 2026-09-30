# 内置 MCP 配置

## 接口与授权（第一版：禅道）

MCP 与现有禅道账号密码连接是独立的服务类型，不复用其授权。系统提供内置模板，
每个项目最多配置一份禅道 MCP；不支持自定义模板、stdio 或启停开关。

- `GET /v1/projects/{projectId}/services/mcp/templates`：成员可读取内置模板，
  返回 `items: [{templateId: "zentao", name: "禅道 MCP", type: "streamableHttp", authorizationHeader: "token"}]`。
  即使项目没有配置服务，也返回该模板；不因此创建数据库记录。
- `POST /v1/projects/{projectId}/services/mcp`：所有者提交
  `{"name":"禅道 MCP","baseUrl":"http://127.0.0.1:9090/zentao/mcp","templateId":"zentao"}`。
  `baseUrl` 是完整 MCP 端点，保留路径及末尾斜杠；仅接受 HTTP/HTTPS，拒绝 URL 内的
  用户名密码、查询参数、片段和空白。token 必须单独授权。重复配置模板返回 409。
- `PATCH /{serviceId}`：仅修改名称；更换 URL 必须删除后重新配置。
- `PUT /{serviceId}/authorization`：当前成员提交 `{"token":"个人 token"}`；token 按现有
  凭据机制加密，保存到本人连接的 `secret_json.token`。不接受账号密码或 API Key。
- 授权更新使用上述 PUT 接口；`DELETE /{serviceId}/authorization` 撤销个人授权，
  `DELETE /{serviceId}` 删除项目服务。撤销只影响本人；删除服务删除所有相关个人
  授权和连接，重新配置时使用新 ID，需重新授权。

目录响应增加可空 `templateId`，MCP 值为 `zentao`，其他服务为 `null`。
`authorization.status=authorized` 对 MCP 仅表示本人已保存配置，不表示连接测试成功；
目录及授权响应均不返回 token。没有专门的连接测试接口。

本期不修改 AIWork 请求、任务派发、Worker 或 nanobot 配置，也不向原有模型选择器
提供 MCP 连接。后续按任务类型绑定，才会使用运行操作人的 token 组装
`tools.mcpServers.zentao = {type: "streamableHttp", url: baseUrl, headers: {token: ...}}`。

新增 `20260926_0016` 初始化迁移，为共享服务增加可空 `template_id` 及
`(project_id, provider, template_id)` 唯一约束；原有非 MCP 服务保持空值。
初始化仍使用 `alembic upgrade head`，不预置项目 URL 或个人凭据。

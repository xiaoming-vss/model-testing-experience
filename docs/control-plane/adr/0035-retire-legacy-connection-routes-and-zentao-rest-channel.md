# ADR 0035：退役旧连接管理路由与禅道 REST 通道

- 状态：已接受
- 日期：2026-11-27
- 取代：—
- 被取代：—
- 关联：[ADR 0023](0023-external-connection-transport-security.md)、[内置 ZenTao-MCP 连接](../builtin-mcp.md)、[实时执行](../realtime-test-execution.md)

## 背景

平台曾同时保留两条禅道接入：旧 REST 账号密码连接器（`services/zentao_auth.py`、`services/zentao_queries.py`、`services/integration_connections/zentao.py`）和项目级 ZenTao-MCP。页面已改用 MCP：项目所有者配置 MCP 服务，成员保存本人 Token，绑定、用例推送和 Bug 同步都通过 MCP 身份完成。旧连接器仍保留认证、资源查询和连接管理路由，但没有生产调用方。

LLM、GitLab、MCP 连接另有一套逐连接管理路由 `/projects/{projectId}/integrations/{provider}/connections`。项目基础服务接口 `/projects/{projectId}/services/{provider}` 已成为页面唯一入口，逐连接路由只剩测试和一些列表查询在使用。两套入口叠加了连接字段更新、凭据加密和个人授权规则。

## 决策

1. 删除禅道 REST 账号密码连接器：移除 `services/zentao_auth.py`、`services/zentao_queries.py`、`services/integration_connections/zentao.py`、`EnsureZentaoToken`、ZenTao 资源查询链和共享服务中的 `zentao` provider。共享服务只接受 `llm`、`gitlab`、`mcp`。
2. 禅道只保留 MCP 通道：MCP 服务仍使用 `templateId: "zentao"`，资源绑定仍使用 `provider: "zentao"`，Bug 推送、用例推送和附件补传继续沿用项目绑定的 MCP 与操作者本人 Token。
3. 删除逐连接管理路由的创建、单条读取、更新、删除和 reauth；保留项目级连接列表 GET，以及 GitLab 群组、仓库、分支三条级联查询 GET。页面通过项目基础服务创建、修改、删除和授权连接。
4. 删除 MCP `instance-reset` 路由及其请求模型；切换禅道实例继续使用编辑配置的 PATCH，并提交 `confirmInstanceSwitch: true`。
5. Studio 删除 `provider === 'zentao'` 的连接分支、表单和类型，只保留 MCP 服务、本人授权和资源绑定。
6. 删除只服务于上述路由的 handler、请求模型、服务方法和测试；新增连接测试改为直接写入数据库，不再通过 HTTP 路由造数。

## 后果

- 旧 REST 禅道连接不再可创建、读取或使用；历史 `integration_connections` 行按 ADR 0014 由空库基线管理，不新增迁移。
- 调用已删除路由的客户端收到 404；项目级列表和 GitLab 级联查询保持原响应形状。
- 禅道凭据只来自成员本人的 MCP Token，平台不再保存或使用账号密码。
- 连接管理只有一套写入路径，减少连接字段更新和授权规则的分叉。

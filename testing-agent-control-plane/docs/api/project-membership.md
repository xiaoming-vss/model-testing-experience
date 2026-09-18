# 项目协作与个人授权接口

## 权限模型

所有接口继续使用 Bearer JWT。已注销账号的旧 JWT 返回 401。项目返回 `role` 和 `permissions`，供前端展示按钮；后端对每次操作独立校验，不能靠隐藏按钮代替鉴权。

| 操作 | owner | member | viewer |
| --- | --- | --- | --- |
| 查看项目、成员、已保存资产、候选和运行报告 | 是 | 是 | 是 |
| 新增、修改、删除需求和用例 | 是 | 是 | 否 |
| 执行测试、AI 生成、审核、导入、重试 | 是 | 是 | 否 |
| 成员管理、项目设置和删除、项目技能维护 | 是 | 否 | 否 |
| GitLab / 禅道项目、迭代、需求资源绑定 | 是 | 否 | 否 |
| 配置和使用本人外部连接 | 是 | 是 | 是（只读外部操作） |
| 读取、维护、使用别人的连接 | 否 | 否 | 否 |

项目列表包含自己拥有或加入的项目。资产权限不依赖创建者；退出后不能继续访问自己创建的旧资产。角色只在对应项目内有效。

数据库以 `projects.user_id` 作为唯一所有者来源，`project_members` 只保存 member/viewer，成员列表合成 owner 行。PyCasbin 使用固定角色和操作策略；用户与角色关系每次从数据库读取，不维护第二套可写策略表。

## 成员管理

以下路径均位于 `/v1`：

| 方法与路径 | 请求 | 行为 |
| --- | --- | --- |
| `GET /projects/{projectId}/members` | 无 | 返回 `items`、`total`；每行含 `userId`、`name`、`role` |
| `POST /projects/{projectId}/members` | `{"name":"精确用户名","role":"member"}` | owner 直接加入已注册用户，role 可为 member/viewer |
| `PATCH /projects/{projectId}/members/{userId}` | `{"role":"viewer"}` | owner 调整非 owner 成员角色 |
| `DELETE /projects/{projectId}/members/{userId}` | 无 | owner 移除成员，成员也可移除自己 |
| `POST /projects/{projectId}/leave` | 无 | 当前非 owner 成员退出 |
| `POST /projects/{projectId}/transfer-ownership` | `{"userId":"已有成员 ID"}` | 新 owner 原子接任，原 owner 变为 member |

不存在用户名返回 404；重复加入返回 409；无对应项目操作权限返回 403。所有者不能直接退出、移除自己或被普通角色修改，返回 409。注销前必须转移或删除全部拥有的项目。转移也遵守目标所有者的项目名称唯一约束。

## 外部个人授权与共享绑定

基础服务连接仍在既有 `/projects/{projectId}/integrations/{provider}/connections` 路径维护，provider 为 `gitlab`、`zentao` 或 `llm`。连接只能由本人读取、修改、删除；访问别人的连接 ID 返回 404。允许项目成员管理本人连接，但这不会增加项目内写权限。

绑定新增 `instanceUrl`。外部资源身份由 provider、规范实例 URL、资源类型及资源 ID 共同决定，数字 ID 在不同服务器之间不合并。规范化包括主机大小写、默认端口和尾部斜线；URL 不包含账号密码。

绑定上的 `connectionId` 仅保留历史兼容信息，不能用于借用创建者的授权。owner 绑定时使用自己的授权验证资源；成员实际访问时选择自己的同实例连接。缺少有效个人连接则拒绝外部操作；只有一个有效候选时可以自动选择，有多个时必须显式指定。删除或失效的连接不会回退到其他成员。

- GitLab 项目绑定群组，需求绑定该群组树内的仓库和分支。创建请求可传 `connectionId`；需求也可用 `instanceUrl` 辅助选择。更新项目绑定用当前 owner 的 `connectionId` 重新验证，不转移旧连接。需求更新可传 `connectionId`、`branch`、`baselineBranch`。
- 禅道项目绑定 project、迭代绑定 execution、需求绑定 story。父子必须同实例，且远端关系正确。项目、迭代、需求绑定的 PATCH 接口可用本人 `connectionId` 重新验证，`remoteResourceId` 可更新；已有下级绑定时不能更换父资源 ID。
- 代码概览 `GET /sprints/{sprintId}/code-overview` 接收可选 `connectionIds` 查询参数，内容是 JSON 对象（`instanceUrl` → 本人 connectionId）。无授权的仓库返回错误和补救说明，不返回实时统计；其他已授权仓库可正常展示。不再复用项目级缓存。
- 禅道功能用例导入、日报快照生成请求可传 `connectionId`。读取已经保存的日报及 bug 明细不触发外部查询。

## AI 执行人与 Worker 契约

创建共享 AI 任务不需要 LLM 密钥，执行请求的 `connectionId` / `llmConnectionId` 必须属于实际操作者且处于 active 状态。代码风险分析另外接受 `gitlabConnectionIds`（`instanceUrl` → 本人连接 ID），每个仓库快照同时包含 `instanceUrl` 和选定连接引用。

人工推进、重新生成、重试接受 `llmConnectionId`；换人操作时必须选择新操作者自己的连接。未显式选择时仅允许复用**仍属于当前操作者且有效**的上一连接，不能复用他人的连接。自动阶段沿用同一次提交的执行人。任务创建者、运行发起人、阶段请求人、审核人分别保留。

Worker 内部接口保留 worker token 鉴权。领取、快照、文档和凭据下发及回调会检查当前任务状态、执行人账号、项目成员关系和个人连接状态。凭据只在有效 claimed/running 任务中发放，终态任务不能再次领取凭据。

退出、被移除、注销和删除连接会使受影响的待执行/执行中任务失败；重新加入不会复活旧队列任务。仅降级为 viewer 不取消此前合法提交的任务，但新的执行、审核、重试会被拒绝。失败后必须由有执行权限的成员配置本人授权并明确重新执行，不自动接管。

已经发送到外部执行器的令牌无法由控制台收回；阻止后续下发不等于撤销第三方令牌或立即终止远端执行。

## 环境密钥与文件

标记 `isSecret` 的环境变量返回 `********`，包括写入响应和读取响应；回传掩码不会覆盖原密钥。只有保存该秘密的用户可修改或使用它，其他成员不能取消秘密标记后读取。共享环境含其他用户的秘密时，执行返回 403，需要使用自己的环境配置。

API 执行的原始请求和运行变量在含秘密时另行加密保存，仅向通过执行人校验的 Worker 发放；项目可读快照、响应、提取结果、断言和错误文本进行脱敏。新提取并持久化的环境变量默认视为执行人的秘密，防止登录结果成为共享授权。未标记的任意业务字符串不自动判定为秘密。

UI 源码归档不再通过无鉴权 `/uploads` 静态目录下载，Worker 使用所属任务的 `/internal/ai-worker/tasks/{taskId}/source-archive`。需求文档沿用受鉴权的用户/任务下载接口。

## 数据库与发布范围

初始迁移 `20260915_0001` 保持冻结，新增成员、环境秘密归属、实例身份、日报明细、加密执行输入迁移。空库执行 `uv run alembic upgrade head`。本功能以新库初始化为发布路径，不承诺旧开发库历史孤儿数据回填。

本仓库交付后端和 OpenAPI 契约；前端成员页面、连接选择 UI 以及外部 Worker 客户端更新在对应仓库完成。生产部署不在本次实施范围。

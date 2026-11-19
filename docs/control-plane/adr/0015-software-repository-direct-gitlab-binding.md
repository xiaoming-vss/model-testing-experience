# 软件仓库直接绑定 GitLab 仓库

- 状态：已接受
- 日期：2026-11-15
- 取代：[ADR 0012](0012-project-interface-library.md) 的「应用仓库与群组解绑」条款、[ADR 0013](0013-software-repository-and-interface-library-api-generation.md) 的项目级 GitLab 群组绑定表述
- 被取代：—
- 关联：[ADR 0012](0012-project-interface-library.md)、[ADR 0013](0013-software-repository-and-interface-library-api-generation.md)

2026-11-15。移除项目级 GitLab 群组绑定；软件仓库在创建与换绑时直接选择 GitLab 连接、群组和代码仓库。本决策取代 [ADR 0012](0012-project-interface-library.md) 中的「应用仓库与群组解绑」条款，以及 [ADR 0013](0013-software-repository-and-interface-library-api-generation.md) 中「项目级 GitLab 群组绑定保持不变」及「无 Git 仓库的项目需先完成 GitLab 群组绑定」的表述。

## 决策

- **移除项目级群组绑定**：项目不再维护 GitLab 群组绑定，也不再提供群组绑定的创建、重新验证和解绑入口。项目级 `/bindings` 路由仅继续服务禅道绑定；提交 `provider=gitlab` 返回明确错误。
- **软件仓库直接绑定**：软件仓库创建与换绑时选择操作者本人的 GitLab 连接、该连接可访问的群组，以及群组树内的代码仓库。后端使用操作者个人授权校验仓库归属和可访问性，不要求项目级群组绑定。
- **群组是选择范围与快照**：`repository_group_id` 保存所选群组标识，`repository_instance_key` 保存实例摘要用于匹配操作者同实例个人授权；两者不再解析项目群组绑定。
- **运行时授权**：代码风险分析、仓库画像、迭代代码概览、UI 生成源码和需求分支校验继续按软件仓库实例解析操作者本人的 GitLab 个人连接，不使用绑定创建者的凭据。
- **解绑保护移除**：删除「仍有软件仓库引用时禁止解绑群组」的校验；群组不再有项目级解绑动作。
- **通用绑定表保留**：`resource_bindings` 继续承载禅道绑定，不删除表、列或唯一约束。历史 GitLab 群组绑定行不迁移、不再读取，仍可通过既有 DELETE 接口清理。
- **无结构变更**：按 [ADR 0014](0014-pre-release-single-baseline.md)，不新增迁移；`software_repositories` 的既有快照列保留，仅同步注释语义。

## 接口

- `POST /v1/projects/{project_id}/software-repositories` 与 `PATCH /v1/software-repositories/{software_repository_id}` 的 `repository` 字段继续使用 `connectionId`、`groupId`、`repositoryId`。
- `GET /v1/projects/{project_id}/integrations/gitlab/connections/{connection_id}/groups` 与 `.../groups/{group_id}/repositories` 继续作为个人连接下的级联选择接口。
- `POST/PATCH /v1/projects/{project_id}/bindings` 不再接受 `provider=gitlab`；禅道绑定契约不变。

## 后果

- 项目设置不再展示 GitLab 群组绑定；GitLab 个人连接仍在基础服务中管理。
- 软件仓库可以直接绑定个人授权范围内的任意群组仓库，不再受项目预绑定群组限制。
- 代码上下文读取链路少一层群组绑定校验，凭据仍严格使用本次操作人的个人授权。
- 遗留 GitLab 群组绑定行成为无业务含义的历史数据，不影响软件仓库读取。

## 拒绝的替代方案

- **保留项目群组绑定但不在 UI 展示**：仍会要求先完成一层隐式配置，软件仓库无法真正独立绑定。
- **删除 `repository_group_id` 列**：群组仍用于选择仓库范围和审计快照，删除后需要额外的仓库命名空间解析，且会增加无必要的结构变更。
- **自动为软件仓库创建项目群组绑定**：会把用户的一次仓库选择变成项目级共享状态，重新引入隐式绑定和删除保护问题。

相关文档：[控制面上下文](../CONTEXT.md)、[数据库结构描述](../database-schema.md)、[软件仓库与接口库生成](0013-software-repository-and-interface-library-api-generation.md)、[Studio 上下文](../../studio/CONTEXT.md)。

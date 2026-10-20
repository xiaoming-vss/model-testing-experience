# 认证与权限模块

## 部署与职责

认证、会话、账号治理和业务授权都在 control-plane 内运行，使用同一业务数据库。
Studio 消费公开接口和能力字段，Worker 使用内部令牌领取任务和获取执行材料。
本次整理不引入独立网关或远程权限服务。

| 职责 | 入口 | 数据与事务责任 |
| --- | --- | --- |
| 本地身份验证 | LocalLoginService | 密码、登录限流、账号锁定；保持认证模式锁与用户锁顺序 |
| LDAP 身份验证 | LdapLoginService | 目录 IO 不持有数据库写锁；提交前重查模式代次与账号版本 |
| 会话 | SessionService | Token 签发、身份验证、单会话注销；全部会话失效由账号事务更新版本 |
| 账号治理 | AuthService、UserAdminService | 注册、资料、改密及跨业务账号删除；事务由调用流程提交 |
| 项目策略 | domain/project_policy.py | 唯一角色动作策略、有效角色计算；不查询数据库 |
| 普通项目访问 | services/project_access.py | 读取当前成员与管理员身份，保留原公共调用入口 |
| 任务执行授权 | worker_authorization.py、integration_authorization.py | 运行发起者、资源归属、本人凭据及授权版本；保留原任务协议 |
| 人工恢复 | integration_recovery.py | 远程查询后，在原事务内锁定并重新检查当前授权事实 |

## 项目角色动作矩阵

| 角色 | read | write | execute | review | manage | project_read | bug_read | bug_handle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| owner | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 |
| member | 是 | 是 | 是 | 是 | 否 | 是 | 是 | 是 |
| viewer | 是 | 否 | 否 | 否 | 否 | 是 | 是 | 否 |
| developer | 否 | 否 | 否 | 否 | 否 | 是 | 是 | 是 |
| 非成员/未知角色 | 否 | 否 | 否 | 否 | 否 | 否 | 否 | 否 |

角色只决定项目动作能力，不能代替资源属于该项目、指派对象资格或本人凭据归属检查。
普通请求及人工恢复将系统超级管理员解析为具备 owner 能力；页面仍显示系统管理员。
集成执行保留现有更窄规则：要求实际项目所有者或具有 write 的成员，不因系统管理员身份自动获得远端写许可。

## 账号和会话矩阵

| 事件/状态 | 浏览器请求 | 已提交任务 |
| --- | --- | --- |
| 正常且 Token 有效 | 按项目动作及资源归属检查 | 按运行发起者与个人授权检查 |
| 单次注销 | 当前 Token 失效，其他会话不变 | 不因此终止 |
| 改密/重置/强制下线 | 旧 Token 版本失效 | 不因此终止 |
| disabled / pending_ldap | 拒绝旧 Token | 不把浏览器状态检查自动套用到已提交任务 |
| 必须改密 | 仅当前信息、改密和注销可访问 | 保留原任务语义 |
| 删除账号 | 不再有有效身份 | 撤销任务授权，历史身份不回收 |
| 项目移除/角色降级 | 按最新成员与动作拒绝 | 按各任务域既有撤销和再检查规则处理 |
| 外部个人授权撤销 | 平台登录不受影响 | 拒绝新的相关执行材料或写许可 |

## 前端核对范围

前端已有 `useProjectAccess`、`ProjectActionButton` 和 `ProjectAccessScope`。
能力展示必须以服务端 permissions 为准，角色标签不产生能力；保留旧接口 read/write 到 Bug 动作的兼容。
成员列表中“所有者不能被移除”和角色标签属于身份约束与展示，不改成通用能力判断。
请求失败时不能继续用缓存能力开放操作。

`isBugOnlyProject` 按“可读 Bug 且不能读完整项目资产”选择受限查询入口，
由 AppShell、Bug 列表、Bug 详情和转派共用。Bug 详情的权限查询失败后，
即使 React Query 仍保留旧数据，也关闭读取、编辑和处理能力。
测试单中实际所有者对执行人分配的特殊规则、成员弹窗中的所有权约束保持原样。

## 改造文件与保留差异

- `services/auth.py` 保留既有路由调用入口，分派给 `services/local_login.py` 和
  `services/ldap_login.py`；注册、资料和改密仍由 AuthService 协调。
- `services/auth_session.py` 统一 `issue_session`、`invalidate_sessions` 和 SessionService。
  `repositories/auth_session.py` 负责会话状态查询与撤销记录。
  `api/deps.py` 只将 Token 和请求上下文交给会话模块。
- `domain/account_policy.py` 提供邮箱归一化和本地密码规则，账号管理、管理员初始化和
  运维 CLI 不再通过登录服务导入这些规则。
- `domain/project_policy.py` 持有唯一 Casbin 策略和有效角色解析。
  `repositories/project_access.py` 负责普通访问查询；原
  `services/project_access.py` 的调用入口继续可用。
- `integration_authorization.py` 和 `integration_recovery.py` 共用纯策略，
  各自保留原加锁查询、顺序和事务范围。没有增加角色缓存或第二份可写策略存储。
- 账号改密、禁用、重置、强制下线、LDAP 关联和对账复用会话版本失效函数，该函数不提交事务。
  认证模式切换仍使用原批量 SQL，在模式切换事务中原子递增版本，不逐个加载账号。
- Token 使用传入的 Settings 签发；生产装配仍使用同一配置中的签名密钥。
  本地用户、管理员和 LDAP 的有效期分别保持既有配置，LDAP 不回退到本地密码。

## 验证

验证日期：2026-10-20。以下命令在 `apps/control-plane/` 执行。

认证和权限基线在重构前、重构后各通过 90 项：

```sh
uv run --locked --extra dev python -m pytest \
  tests/test_auth_contract.py tests/test_access_token_revocation.py \
  tests/test_local_account_management.py tests/test_project_membership_api.py \
  tests/test_developer_access.py tests/test_integration_authorization.py \
  tests/test_ldap_login.py tests/test_ldap_lifecycle_api.py \
  tests/test_architecture_layers.py -q
```

新增矩阵与会话测试验证数据库角色、管理员场景差异、禁用与删除的执行授权区别、
各类会话有效期、独立登录、事务回滚和跨账号注销拒绝。原回归覆盖跨项目资源、
成员移除、角色降级、本人凭据、改密、禁用/启用和删除账号。

扩大回归通过 242 项，跳过 1 项真实 MySQL 队列锁检查：

```sh
uv run --locked --extra dev python -m pytest \
  tests/test_project_policy.py tests/test_auth_session.py \
  tests/test_ldap_accounts.py tests/test_ldap_reconcile.py tests/test_ldap_cutover.py \
  tests/test_ldap_settings_api.py tests/test_ldap_settings_admin.py tests/test_ldap_settings.py \
  tests/test_super_admin_seed.py tests/test_integration_recovery.py \
  tests/test_integration_jobs.py tests/test_integration_bug_api.py \
  tests/test_platform_access_regressions.py tests/test_stored_file_access.py \
  tests/test_worker_contract.py tests/test_worker_queue_storage.py \
  tests/test_app_contract.py tests/test_go_field_contracts.py tests/test_full_route_parity.py -q
```

修改范围的 `ruff check`、`ruff format --check` 和
`mypy --python-version 3.12 --check-untyped-defs` 通过；
类型检查覆盖本次 17 个源码文件（上述模块及改动的账号治理、LDAP、CLI 和 API 装配文件）。
最终核对将新模块的账号状态比较统一为既有 `AccountStatus` / `AuthSource` 枚举后，
再次运行 `test_auth_contract.py`、`test_auth_session.py` 和
`test_local_account_management.py`，28 项通过；对应三个模块的 Ruff、格式和类型检查再次通过。

Studio 在 `apps/studio/` 执行 `npm run verify`，类型检查、全项目 ESLint、主题检查和构建通过。
以下测试共 28 项通过：

```sh
npm test -- \
  src/features/projects/hooks/useProjectAccess.test.ts \
  src/features/projects/components/ProjectMembership.test.tsx \
  src/app/layouts/AppShell.developer.test.tsx \
  src/app/layouts/AppShell.projectMenu.test.tsx \
  src/features/bugs/pages/BugListPage.test.tsx
npm test -- src/features/bugs/hooks/useBugDetail.access.test.tsx
```

构建仍有既有大包体积提示；测试依赖有弃用和测试用短 JWT 密钥提示。
本次没有数据库迁移、部署编排、外部目录协议或远端写入协议变更。
SQLite/模拟目录不证明真实 MySQL 行锁、LDAP ACL 或外部写入行为。

最后复验矩阵并调用可选 MySQL 检查：

```sh
uv run --locked --extra dev python -m pytest \
  tests/test_project_policy.py tests/test_auth_session.py \
  tests/test_ldap_mysql.py tests/test_integration_jobs_mysql.py -q -rs
```

结果为 12 项通过、13 项跳过。跳过原因为未设置指向空的可丢弃测试库的
`CONTROL_PLANE_TEST_DATABASE_URL`；没有借用开发或生产业务库进行验证。
扩大回归中的 `test_mysql_claim_skips_locked_task` 使用同一测试库要求，单独以
`pytest tests/test_worker_queue_storage.py::test_mysql_claim_skips_locked_task -q -rs`
复核后确认同样因此跳过。总计 332 项不同的后端测试通过，14 项 MySQL 检查跳过；
最后 12 项矩阵复验不重复计数。
本次未修改编排文件，因此没有运行根目录编排 unittest 或 Compose 配置生成。

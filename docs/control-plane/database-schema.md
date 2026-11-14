# 数据库结构描述

控制面数据库保存项目、迭代、需求、正式测试资产、AI 候选及审核记录、测试执行结果、个人授权、文件元数据、Bug 处理历史、账号登录限流记录和独立集成执行账本。

MySQL 8.4 没有库级 `COMMENT` 属性，库的用途在本文说明；表和字段的业务含义使用原生 `COMMENT` 保存。注释由 `src/testing_agent/models/` 内的 SQLAlchemy `__table_args__["comment"]` 和 `mapped_column(comment=...)` 定义，可被数据库管理工具及 `information_schema` 读取。

在数据库连接中查询：

```sql
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

## v1 冻结基线

`Base.metadata` 是 v1 的唯一结构来源，`alembic/versions/20261103_0001_v1_baseline.py` 是从该模型生成的唯一冻结迁移，创建全部业务表和 `alembic_version`。v1 只支持空库初始化：`alembic upgrade head` 建立完整结构，downgrade 仅用于空库测试往返，按依赖逆序删除全部表。

后续表、字段或注释变更必须新增迁移，不能改写 baseline。新增表或字段时，在模型定义旁填写业务含义，并随新迁移一起落库；说明应包含必要的单位、状态值、标识归属、快照用途和历史兼容约定，个人凭据的说明必须与实际存储方式一致。`description` 等业务列保存业务内容，其列注释解释该列本身的用途。

`tests/test_initial_schema_migration.py` 验证唯一 baseline、空库升级、降级与再次升级；`tests/test_schema_comments.py` 验证模型注释完整性及真实 MySQL 注释与模型一致；`tests/test_mysql_initialization.py` 在明确指定的空、可丢弃测试库（库名必须以 `_test` 结尾）验证 MySQL 初始化和结构与模型一致。SQLite 不支持持久化表和字段注释，结构断言只覆盖表和字段。

本地开发库 `testing-agent-control-plane-b` 是唯一保留数据的例外：确认结构与 baseline 零差异且行数不变后，使用一次性 `alembic stamp --purge 20261103_0001` 写入版本号，不执行 DDL。详见[部署说明](../deployment.md#本地已有库的一次性-stamp)。

## LDAP 身份与认证切换

- `users.auth_source`：`local` / `ldap`，本地账号为 `local`；`external_id` 为可空的规范 UUID 文本，本地账号使用 NULL。两列组合唯一，阻止同一目录身份关联多个账号。`status` 包含 `pending_ldap`，普通业务鉴权仅允许 `active`。
- `login_rate_limits.auth_method`：`local` / `ldap`；唯一键为认证方式、用户名与 IP，防止 LDAP 同名失败锁住管理员本地入口。
- `auth_runtime` 是主键为 1 的单例。`mode`、`fingerprint`、`generation` 记录已完成的认证配置切换；`changed_at` 为切换时间；`reconcile_owner`、`reconcile_until` 协调对账租约。配置摘要不公开给浏览器，不替代配置源。

账号状态转换与会话撤销由显式切换事务执行，不由迁移或每次启动重复执行。写事务按运行状态行、用户行的顺序加锁，目录网络调用不持有用户写锁。恢复、回退及部署步骤见 [LDAP 统一认证](ldap-authentication.md)。

## UI 环境变量

- `api_environments.kind`：`api` / `ui`，默认 `api`；唯一约束为 `(project_id, kind, name)`，两类环境可以同名。
- `api_environment_vars.var_key`：MySQL 下使用 `utf8mb4_bin`，变量引用区分大小写；唯一索引为 `(environment_id, var_key)`。
- `ui_test_case_runs`、`ui_test_suite_runs`：包含 `environment_id`、`environment_name`（名称快照）、`used_variables_json`、`variable_writes_json` 与加密的 `private_payload`。

表名保留 `api_` 前缀，因为改名会牵动 API 自动化的全部代码。运行协议与隐私规则见 [UI 环境变量与后置提取](ui-environment-variables.md)。

## 接口库与应用

- `api_apps`：项目级接口应用，保存名称、说明、应用级 `base_path`、启用状态和 `version`。可选 GitLab 仓库以 `repository_project_id`、`repository_path`、`repository_name`、`repository_instance_url` 快照保存；`(project_id, name)` 唯一，删除应用前必须没有接口。
- `api_interfaces`：接口定义，保存方法、规范化相对路径、`path_key`（路径 SHA-256）、请求头与 Path/Query 参数 JSON、请求体、单个默认成功响应、标签、说明、启用状态、版本和来源快照。接口身份由 `(app_id, method, path_key)` 唯一约束确定，避免 utf8mb4 长路径索引限制；应用外键为 `RESTRICT`。
- `api_interface_requirements`：接口与需求的关联表，接口外键和需求外键均 `CASCADE`，`(interface_id, requirement_id)` 唯一；迭代通过需求归属推导，不在关联表冗余保存。

接口删除为业务硬删除，使用统一的 `ResourceDeletion`；导入提交在单一事务内锁定应用与接口行、校验来源摘要和逐项版本，并保留仅库中存在的接口。接口应用引用 GitLab 群组时阻止该群组解绑，直到引用被清除或替换。结构决策见 [ADR 0012](adr/0012-project-interface-library.md)。

## AI 执行、阶段尝试与历史

统一 AI 执行模型使用以下表：

- `ai_generate_tasks`：任务定义、归属、创建者和来源配置。
- `ai_executions`：一次用户或系统发起的执行身份、发起者和创建时间；独立多阶段执行另存聚合状态、当前阶段、检查点、初始快照和起止时间。
- `ai_generation_stages`：任务的稳定阶段，保存当前候选、活动尝试、版本计数和 UI 输入批次；不保存可推导的执行状态或审核副本。
- `ai_generation_attempts`：阶段内的生成、修订或人工编辑尝试，保存冻结输入、输出、错误和可选执行关联；人工编辑可以没有 Worker 队列。
- `ai_generate_stage_versions`：审核通过后产生的不可变正文及来源快照，版本号在任务阶段内不复用。
- `ai_generate_version_imports`：正式资产导入来源，只引用一个已审核版本或一个独立候选尝试，并记录目标、变更用例和上游快照。

阶段尝试不保存 `progress_json` 或 `remediation`；阶段不保存可推导的执行状态和审核副本。公开 AI 接口的 `runId` 是执行 ID，AI Worker 队列和回传的标识是 `attemptId`。执行身份与阶段模型的完整决策见 [ADR 0010](adr/0010-unified-ai-execution.md)，历史删除规则见[生成链文档](generation-chain.md#历史与删除)。

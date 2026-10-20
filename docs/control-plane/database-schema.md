# 数据库结构描述

控制面数据库保存项目、迭代、需求、正式测试资产、AI 候选及审核记录、测试执行结果、个人授权、文件元数据、Bug 处理历史、账号登录限流记录和独立集成执行账本。

MySQL 8.4 没有库级 `COMMENT` 属性，库的用途在本文说明；表和字段的业务含义使用原生 `COMMENT` 保存。注释由 `src/testing_agent/models/` 内的 SQLAlchemy `__table_args__["comment"]` 和 `mapped_column(comment=...)` 定义，可被数据库管理工具及 `information_schema` 读取。

迁移 `20261007_0034` 覆盖当时的 48 张业务表、639 个业务字段，以及 `alembic_version` 表和版本号字段。迁移中的注释目录是固定快照，不导入后续会变化的模型；MySQL 升级时读取既有字段类型、字符集、排序规则、默认值、可空性和自增属性，再修改注释。回退仅清除仍与本次迁移一致的注释，保留迁移后人工改写的说明。SQLite 不支持持久化表和字段注释，此迁移在 SQLite 上不执行结构修改。

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

新增表或字段时，在模型定义旁填写业务含义，并随新迁移一起落库。说明应包含必要的单位、状态值、标识归属、快照用途和历史兼容约定；个人凭据的说明必须与实际存储方式一致。`description` 等业务列保存业务内容，其列注释解释该列本身的用途。

`tests/test_schema_comments.py` 验证模型注释完整性；真实 MySQL 的空库结构对比检查模型与迁移的一致性。后续模型演进时保留固定迁移原文，新字段或注释修订由后续迁移负责。真实 MySQL 回归使用明确指定的空、可丢弃测试库（库名必须以 `_test` 结尾），覆盖注释升级、回退、人工改写保护、字段属性和约束保留及业务行保留；同时运行 `test_initial_schema_migration.py` 验证空库初始化与 SQLite 回退。

## LDAP 身份与认证切换

迁移 `20261020_0041` 在现有本地账号管理迁移之后增加：

- `users.auth_source`：`local` / `ldap`，存量默认本地；`external_id` 为可空的规范 UUID 文本，本地账号使用 NULL。两列组合唯一，阻止同一目录身份关联多个账号。`status` 新增 `pending_ldap`，普通业务鉴权仅允许 `active`。
- `login_rate_limits.auth_method`：`local` / `ldap`，存量默认本地；唯一键变为认证方式、用户名与 IP，防止 LDAP 同名失败锁住管理员本地入口。
- 邮箱注释对齐当前账号规则，保留原字段类型、可空性和默认值；不清理旧用户或改变其身份。

迁移 `20261020_0042` 新建 `auth_runtime` 单例（主键 1），初始为本地模式。`mode`、`fingerprint`、`generation` 记录已完成的认证配置切换；`changed_at` 为切换时间；`reconcile_owner`、`reconcile_until` 协调对账租约。配置摘要不公开给浏览器，不替代配置源。

账号状态转换与会话撤销由显式切换事务执行，不由迁移或每次启动重复执行。写事务按运行状态行、用户行的顺序加锁，目录网络调用不持有用户写锁。恢复、回退及部署步骤见 [LDAP 统一认证](ldap-authentication.md)。
